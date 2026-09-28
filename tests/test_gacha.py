from __future__ import annotations

import asyncio

import pytest

from aniflow.agnes.key_pool import KeyPool
from aniflow.models import VideoResult, VideoTask
from aniflow.pipeline.gacha import (
    COMPLETED,
    CREATED,
    FAILED,
    Draw,
    GachaLedger,
    RateLimiter,
    ShotSpec,
    VideoGachaEngine,
)


class FakeVideoClient:
    """Stand-in for AgnesVideoClient with scriptable failures."""

    def __init__(self, *, fail_creates: int = 0, fail_polls: set[str] | None = None) -> None:
        self.created: list[dict] = []
        self.polled: list[str] = []
        self._fail_creates = fail_creates
        self._fail_polls = fail_polls or set()
        self._n = 0

    async def create_keyframe_task(self, *, api_key, prompt, **kwargs) -> VideoTask:
        self._n += 1
        if self._n <= self._fail_creates:
            raise RuntimeError("transient upstream error")
        vid = f"video_{self._n}"
        self.created.append({"api_key": api_key, "prompt": prompt, "video_id": vid, **kwargs})
        return VideoTask(video_id=vid, status="queued", raw={})

    async def wait_for_result(self, *, api_key, video_id, **kwargs) -> VideoResult:
        self.polled.append(video_id)
        if video_id in self._fail_polls:
            raise RuntimeError("generation failed")
        return VideoResult(
            video_id=video_id,
            status="completed",
            video_url=f"https://media.example/{video_id}.mp4",
        )


def make_engine(client, tmp_path=None, **kw):
    ledger = GachaLedger(tmp_path / "ledger.json" if tmp_path else None)
    return VideoGachaEngine(
        key_pool=KeyPool(["k1", "k2", "k3"]),
        video_client=client,
        ledger=ledger,
        max_requests_per_minute=0,  # disable pacing in tests
        **kw,
    )


SHOT = ShotSpec(
    shot_id="s1",
    prompt="雪所长盯着微波炉转盘",
    first_frame_url="https://media.example/a.png",
    last_frame_url="https://media.example/b.png",
    seconds=8,
)


def test_every_account_is_used_at_least_once():
    client = FakeVideoClient()
    engine = make_engine(client, draws_per_shot=3)
    report = asyncio.run(engine.draw_shot(SHOT))
    assert len(report.completed) == 3
    assert {c["api_key"] for c in client.created} == {"k1", "k2", "k3"}


def test_draw_count_floors_at_account_count():
    # Asking for 1 draw with 3 accounts still uses all 3.
    client = FakeVideoClient()
    engine = make_engine(client, draws_per_shot=1)
    report = asyncio.run(engine.draw_shot(SHOT))
    assert len(report.completed) == 3


def test_shot_duration_and_frames_reach_the_client():
    client = FakeVideoClient()
    engine = make_engine(client, draws_per_shot=1)
    asyncio.run(engine.draw_shot(SHOT))
    first = client.created[0]
    assert first["seconds"] == 8
    assert first["first_frame_url"] == "https://media.example/a.png"
    assert first["last_frame_url"] == "https://media.example/b.png"


def test_create_is_retried_then_succeeds():
    client = FakeVideoClient(fail_creates=2)
    engine = make_engine(client, draws_per_shot=3, create_attempts=3)
    report = asyncio.run(engine.draw_shot(SHOT))
    # 2 transient failures are absorbed by retry; all 3 draws still land.
    assert len(report.completed) == 3
    assert len(report.failed) == 0


def test_create_failure_is_recorded_not_swallowed():
    client = FakeVideoClient(fail_creates=99)
    engine = make_engine(client, draws_per_shot=3, create_attempts=2)
    report = asyncio.run(engine.draw_shot(SHOT))
    assert len(report.completed) == 0
    assert len(report.failed) == 3
    assert all("create failed" in d.error for d in report.failed)


def test_partial_poll_failure_keeps_good_draws():
    client = FakeVideoClient(fail_polls={"video_2"})
    engine = make_engine(client, draws_per_shot=3)
    report = asyncio.run(engine.draw_shot(SHOT))
    assert len(report.completed) == 2
    assert len(report.failed) == 1


def test_video_ids_are_persisted_before_polling(tmp_path):
    """The whole point of two-phase: a crash after create must not lose IDs."""
    client = FakeVideoClient()
    engine = make_engine(client, tmp_path, draws_per_shot=3)
    asyncio.run(engine.draw_shot(SHOT))
    reloaded = GachaLedger(tmp_path / "ledger.json")
    reloaded.load()
    assert len(reloaded.draws) == 3
    assert all(d.video_id for d in reloaded.draws.values())
    assert all(d.status == COMPLETED for d in reloaded.draws.values())


def test_resume_repolls_only_unresolved_draws(tmp_path):
    ledger = GachaLedger(tmp_path / "ledger.json")
    ledger.upsert(Draw("s1-d1", "s1", 0, "account-1", status=CREATED, video_id="video_1"))
    ledger.upsert(
        Draw(
            "s1-d2",
            "s1",
            1,
            "account-2",
            status=COMPLETED,
            video_id="video_2",
            video_url="https://media.example/video_2.mp4",
        )
    )
    ledger.save()

    client = FakeVideoClient()
    engine = VideoGachaEngine(
        key_pool=KeyPool(["k1", "k2", "k3"]),
        video_client=client,
        ledger=ledger,
        max_requests_per_minute=0,
    )
    report = asyncio.run(engine.resume())
    # Only the CREATED one is polled again; the COMPLETED one is untouched.
    assert client.polled == ["video_1"]
    assert len(report.completed) == 2


def test_resume_does_not_redraw_terminal_results(tmp_path):
    client = FakeVideoClient()
    engine = make_engine(client, tmp_path, draws_per_shot=3)
    asyncio.run(engine.draw_shot(SHOT))
    created_first_pass = len(client.created)
    # Re-running the same shot must not spend quota again.
    asyncio.run(engine.draw_shot(SHOT))
    assert len(client.created) == created_first_pass


def test_per_key_concurrency_is_bounded():
    peak = {"n": 0, "max": 0}

    class SlowClient(FakeVideoClient):
        async def create_keyframe_task(self, **kw):
            peak["n"] += 1
            peak["max"] = max(peak["max"], peak["n"])
            await asyncio.sleep(0.01)
            peak["n"] -= 1
            return await super().create_keyframe_task(**kw)

    client = SlowClient()
    engine = VideoGachaEngine(
        key_pool=KeyPool(["k1"]),  # single key => semaphore must bind
        video_client=client,
        max_requests_per_minute=0,
        max_concurrent_per_key=2,
        draws_per_shot=6,
    )
    asyncio.run(engine.draw_shot(SHOT))
    assert peak["max"] <= 2


def test_rate_limiter_spaces_calls():
    limiter = RateLimiter(600)  # 0.1s apart

    async def run():
        import time as _t

        start = _t.monotonic()
        for _ in range(3):
            await limiter.acquire()
        return _t.monotonic() - start

    assert asyncio.run(run()) >= 0.18  # 2 gaps of 0.1s


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"first_frame_url": None, "last_frame_url": None}, "first_frame_url or last_frame_url"),
        ({"seconds": 3}, "seconds must be 4..12"),
        ({"seconds": 13}, "seconds must be 4..12"),
        ({"prompt": "   "}, "prompt is required"),
    ],
)
def test_shot_validation_matches_official_contract(kwargs, message):
    base = {
        "shot_id": "s1",
        "prompt": "p",
        "first_frame_url": "https://media.example/a.png",
        "last_frame_url": None,
        "seconds": 5,
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        ShotSpec(**base).validate()


def test_single_frame_shots_are_valid():
    # Official contract: keyframe needs at least ONE of first/last, not both.
    ShotSpec("s", "p", first_frame_url="https://x/a.png").validate()
    ShotSpec("s", "p", last_frame_url="https://x/b.png").validate()


# --- Live-API-informed behaviour (verified against Agnes on 2026-09-28) ---


def test_each_key_gets_its_own_rate_limiter():
    """9 independent accounts must not be serialised behind one global limiter."""
    client = FakeVideoClient()
    engine = VideoGachaEngine(
        key_pool=KeyPool([f"k{i}" for i in range(9)]),
        video_client=client,
        max_requests_per_minute=16,
        draws_per_shot=9,
    )
    assert len(engine._limiters) == 9
    assert len({id(v) for v in engine._limiters.values()}) == 9


def test_nine_accounts_are_all_used():
    client = FakeVideoClient()
    engine = VideoGachaEngine(
        key_pool=KeyPool([f"k{i}" for i in range(9)]),
        video_client=client,
        max_requests_per_minute=0,
        draws_per_shot=9,
    )
    report = asyncio.run(engine.draw_shot(SHOT))
    assert len(report.completed) == 9
    assert {c["api_key"] for c in client.created} == {f"k{i}" for i in range(9)}


@pytest.mark.parametrize(
    "message",
    [
        "Agnes API HTTP 503: video queue is full, please retry later",
        "video_queue_full",
        "Agnes API HTTP 503",
    ],
)
def test_queue_full_is_recognised(message):
    from aniflow.pipeline.gacha import is_queue_full

    assert is_queue_full(RuntimeError(message))


@pytest.mark.parametrize(
    "message",
    ["Agnes API HTTP 400: size must be 720P", "connection reset", "invalid api key"],
)
def test_non_queue_errors_are_not_treated_as_saturation(message):
    from aniflow.pipeline.gacha import is_queue_full

    assert not is_queue_full(RuntimeError(message))


def test_queue_full_uses_long_backoff_and_is_labelled():
    """Saturation must be reported as queue_full, not as a broken shot."""
    slept: list[float] = []

    class QueueFullClient(FakeVideoClient):
        async def create_keyframe_task(self, **kw):
            raise RuntimeError("Agnes API HTTP 503: video queue is full, please retry later")

    async def run():
        import aniflow.pipeline.gacha as g

        real_sleep = asyncio.sleep

        async def fake_sleep(d):
            slept.append(d)
            await real_sleep(0)

        g.asyncio.sleep = fake_sleep
        try:
            engine = VideoGachaEngine(
                key_pool=KeyPool(["k1"]),
                video_client=QueueFullClient(),
                max_requests_per_minute=0,
                draws_per_shot=1,
                create_attempts=3,
                queue_full_backoff_seconds=45.0,
            )
            return await engine.draw_shot(SHOT)
        finally:
            g.asyncio.sleep = real_sleep

    report = asyncio.run(run())
    assert len(report.failed) == 1
    assert "queue_full" in report.failed[0].error
    # Minutes-horizon backoff, not the 8s network-blip horizon.
    assert slept == [45.0, 90.0]
