from __future__ import annotations

import asyncio

import httpx
import pytest

from aniflow.queue_probe import (
    CAPACITY_AVAILABLE,
    INCONCLUSIVE_SATURATED,
    NO_KEYS,
    PER_ACCOUNT,
    Attempt,
    Round,
    decide,
    has_audio_track,
    run_round,
)


def make_round(index: int, pattern: list[bool], code: str = "video_queue_full") -> Round:
    r = Round(index=index, started_at=0.0)
    r.attempts = [
        Attempt(f"account-{i + 1}", ok, video_id=f"v{i}" if ok else None,
                code=None if ok else code, http_status=200 if ok else 503)
        for i, ok in enumerate(pattern)
    ]
    return r


# --- the verdict logic is the whole product; test it hard -----------------


def test_mixed_round_proves_per_account():
    """Some accepted AND some queue_full at the same instant is only possible
    if the limit is enforced per account."""
    assert decide([make_round(1, [True, False, False])]) == PER_ACCOUNT


def test_mixed_in_any_round_is_enough():
    rounds = [
        make_round(1, [False, False, False]),
        make_round(2, [False, True, False]),  # the smoking gun
        make_round(3, [False, False, False]),
    ]
    assert decide(rounds) == PER_ACCOUNT


def test_all_rejected_is_inconclusive_not_global():
    """Honesty check: uniform rejection cannot distinguish global saturation
    from every account being individually saturated."""
    rounds = [make_round(i, [False] * 9) for i in range(1, 4)]
    assert decide(rounds) == INCONCLUSIVE_SATURATED


def test_all_accepted_is_capacity_not_a_verdict():
    rounds = [make_round(1, [True] * 9)]
    assert decide(rounds) == CAPACITY_AVAILABLE


def test_no_rounds_means_no_keys():
    assert decide([]) == NO_KEYS


def test_rejection_that_is_not_queue_full_does_not_prove_per_account():
    """A 401 next to a success says nothing about queueing."""
    r = Round(index=1, started_at=0.0)
    r.attempts = [
        Attempt("account-1", True, video_id="v1", http_status=200),
        Attempt("account-2", False, code="invalid_api_key", http_status=401),
    ]
    assert not r.is_mixed
    assert decide([r]) == CAPACITY_AVAILABLE


def test_round_helpers():
    r = make_round(1, [True, False, True])
    assert len(r.accepted) == 2
    assert len(r.rejected) == 1
    assert r.is_mixed


# --- transport behaviour ---------------------------------------------------


def test_run_round_fires_every_key_and_parses_both_outcomes():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        seen.append(auth)
        body = httpx.Request  # noqa: F841
        if auth.endswith("k2"):
            return httpx.Response(200, json={"video_id": "video_ok", "status": "queued"})
        return httpx.Response(
            503, json={"code": "video_queue_full", "message": "video queue is full"}
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await run_round(
                client,
                base_url="https://api.test/v1",
                keys=["k1", "k2", "k3"],
                model="agnes-video-2.5-flash",
                seconds=8,
                aspect_ratio="9:16",
                index=1,
            )

    rnd = asyncio.run(run())
    assert len(seen) == 3  # every key fired
    assert len(rnd.accepted) == 1
    assert rnd.accepted[0].account_label == "account-2"
    assert all(a.is_queue_full for a in rnd.rejected)
    assert rnd.is_mixed
    assert decide([rnd]) == PER_ACCOUNT


def test_probe_uses_text_mode_so_no_media_layer_is_required():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _j

        captured.update(_j.loads(request.content))
        return httpx.Response(200, json={"video_id": "v"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await run_round(
                client, base_url="https://api.test/v1", keys=["k"],
                model="agnes-video-2.5-flash", seconds=8, aspect_ratio="9:16", index=1,
            )

    asyncio.run(run())
    assert captured["mode"] == "text"
    # text mode forbids these; sending them would be an HTTP 400
    for forbidden in ("first_frame", "last_frame", "images", "audios", "videos"):
        assert forbidden not in captured
    assert captured["size"] == "720P"
    assert captured["seconds"] == "8"  # string per official contract
    assert captured["aspect_ratio"] == "9:16"


def test_network_error_is_recorded_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await run_round(
                client, base_url="https://api.test/v1", keys=["k"],
                model="m", seconds=8, aspect_ratio="9:16", index=1,
            )

    rnd = asyncio.run(run())
    assert not rnd.attempts[0].accepted
    assert "ConnectError" in (rnd.attempts[0].detail or "")


# --- audio detection -------------------------------------------------------


def test_audio_detection_finds_sound_handler(tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"\x00" * 100 + b"hdlr" + b"\x00" * 8 + b"soun" + b"\x00" * 50)
    assert has_audio_track(f) is True


def test_audio_detection_reports_video_only(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"\x00" * 100 + b"hdlr" + b"\x00" * 8 + b"vide" + b"\x00" * 50)
    assert has_audio_track(f) is False


def test_audio_detection_returns_none_when_unknown(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"\x00" * 200)
    assert has_audio_track(f) is None


@pytest.mark.parametrize("missing", ["nope.mp4"])
def test_audio_detection_handles_missing_file(tmp_path, missing):
    assert has_audio_track(tmp_path / missing) is None
