"""Multi-account video gacha engine.

This replaces the naive `CandidateGenerator` fire-and-forget pattern.

Why this exists
---------------
AniFlow's single biggest production advantage is that the owner holds several
independent Agnes accounts, and Agnes Video 2.5 Flash is currently free. That
makes it cheap to draw many candidates ("抽卡") for the same shot and keep the
best one. But the naive implementation had four production-fatal properties:

1. Create and poll were coupled per candidate, so a crash or a timeout lost the
   `video_id` of a task that was still running server-side. The draw was gone
   but the quota was already spent.
2. No rate limiting. 9 keys x 5 draws fired 45 simultaneous requests and tripped
   upstream limits, turning free capacity into failures.
3. No retry on the create call, so one transient network blip silently reduced
   the candidate pool.
4. No resume. Re-running after any interruption re-drew everything from zero.

Design
------
Phase 1 (create): submit every draw, persisting each `video_id` to the ledger
the moment the server accepts it. Nothing is lost after this point.
Phase 2 (poll): resolve every recorded `video_id` independently.

Because the phases are separate and the ledger is written between them, the
engine can be killed at any moment and resumed without re-spending quota.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aniflow.agnes.key_pool import KeyPool, KeySlot
from aniflow.agnes.video import AgnesVideoClient

# Draw lifecycle states.
PENDING = "pending"  # not submitted yet
CREATED = "created"  # accepted by Agnes, video_id known, result unknown
COMPLETED = "completed"  # finished, video_url known
FAILED = "failed"  # terminal failure


@dataclass(slots=True)
class ShotSpec:
    """One shot to draw candidates for.

    Agnes `keyframe` mode requires at least one of first/last frame, and
    forbids `images`/`audios`/`videos`. Duration is a string "4".."12" upstream;
    it is kept as an int here and stringified at the client boundary.
    """

    shot_id: str
    prompt: str
    first_frame_url: str | None = None
    last_frame_url: str | None = None
    seconds: int = 5
    aspect_ratio: str = "9:16"

    def validate(self) -> None:
        if not self.shot_id:
            raise ValueError("shot_id is required")
        if not self.prompt.strip():
            raise ValueError(f"{self.shot_id}: prompt is required")
        if not self.first_frame_url and not self.last_frame_url:
            raise ValueError(
                f"{self.shot_id}: keyframe mode needs first_frame_url or last_frame_url"
            )
        if not 4 <= self.seconds <= 12:
            raise ValueError(f"{self.shot_id}: seconds must be 4..12, got {self.seconds}")


@dataclass(slots=True)
class Draw:
    """A single candidate draw. Serialised into the ledger."""

    draw_id: str
    shot_id: str
    key_index: int
    account_label: str
    status: str = PENDING
    video_id: str | None = None
    video_url: str | None = None
    seed: int | None = None
    error: str | None = None
    created_at: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (COMPLETED, FAILED)


class RateLimiter:
    """Async token bucket spacing calls evenly across a minute.

    Agnes-family tooling reports a ~16 req/min ceiling. Spacing requests is
    friendlier than bursting and then backing off.
    """

    def __init__(self, max_per_minute: int) -> None:
        self._interval = 60.0 / max_per_minute if max_per_minute > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self._interval
        if wait > 0:
            await asyncio.sleep(wait)


class GachaLedger:
    """Crash-safe record of every draw, keyed by draw_id."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.draws: dict[str, Draw] = {}

    def load(self) -> None:
        if not self.path or not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.draws = {d["draw_id"]: Draw(**d) for d in raw.get("draws", [])}

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"draws": [asdict(d) for d in self.draws.values()]}
        # Atomic replace so a kill mid-write cannot corrupt the ledger.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def upsert(self, draw: Draw) -> None:
        self.draws[draw.draw_id] = draw

    def for_shot(self, shot_id: str) -> list[Draw]:
        return [d for d in self.draws.values() if d.shot_id == shot_id]


@dataclass(slots=True)
class GachaReport:
    completed: list[Draw] = field(default_factory=list)
    failed: list[Draw] = field(default_factory=list)
    unresolved: list[Draw] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = len(self.completed) + len(self.failed) + len(self.unresolved)
        return len(self.completed) / total if total else 0.0


class VideoGachaEngine:
    """Draws N video candidates per shot across every configured account."""

    def __init__(
        self,
        *,
        key_pool: KeyPool,
        video_client: AgnesVideoClient,
        ledger: GachaLedger | None = None,
        draws_per_shot: int = 5,
        max_requests_per_minute: int = 16,
        max_concurrent_per_key: int = 2,
        create_attempts: int = 3,
        poll_seconds: float = 1.5,
        poll_timeout_seconds: float = 900.0,
    ) -> None:
        self.key_pool = key_pool
        self.video_client = video_client
        self.ledger = ledger or GachaLedger()
        self.draws_per_shot = draws_per_shot
        self.create_attempts = create_attempts
        self.poll_seconds = poll_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self._limiter = RateLimiter(max_requests_per_minute)
        self._key_locks = {
            slot.index: asyncio.Semaphore(max_concurrent_per_key)
            for slot in key_pool.all_slots()
        }

    def _plan(self, shot: ShotSpec, base_seed: int | None) -> list[Draw]:
        """Assign draws round-robin so every account is used at least once."""
        slots = self.key_pool.all_slots()
        count = max(self.draws_per_shot, len(slots))
        planned: list[Draw] = []
        for i in range(count):
            slot = slots[i % len(slots)]
            draw_id = f"{shot.shot_id}-d{i + 1}"
            existing = self.ledger.draws.get(draw_id)
            if existing and existing.is_terminal:
                planned.append(existing)  # resume: keep terminal results
                continue
            planned.append(
                existing
                or Draw(
                    draw_id=draw_id,
                    shot_id=shot.shot_id,
                    key_index=slot.index,
                    account_label=slot.label,
                    seed=(base_seed + i) if base_seed is not None else None,
                )
            )
        return planned

    def _slot_for(self, draw: Draw) -> KeySlot:
        return self.key_pool.all_slots()[draw.key_index]

    async def _create_one(self, shot: ShotSpec, draw: Draw) -> None:
        if draw.status != PENDING or draw.video_id:
            return
        slot = self._slot_for(draw)
        last_error: Exception | None = None
        for attempt in range(1, self.create_attempts + 1):
            try:
                async with self._key_locks[slot.index]:
                    await self._limiter.acquire()
                    task = await self.video_client.create_keyframe_task(
                        api_key=slot.api_key,
                        prompt=shot.prompt,
                        first_frame_url=shot.first_frame_url,
                        last_frame_url=shot.last_frame_url,
                        seconds=shot.seconds,
                        aspect_ratio=shot.aspect_ratio,
                        seed=draw.seed,
                    )
                draw.video_id = task.video_id
                draw.status = CREATED
                draw.created_at = time.time()
                draw.error = None
                return
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                last_error = exc
                if attempt < self.create_attempts:
                    await asyncio.sleep(min(2.0 * attempt, 8.0))
        draw.status = FAILED
        draw.error = f"create failed after {self.create_attempts} attempts: {last_error}"

    async def _poll_one(self, draw: Draw) -> None:
        if draw.status != CREATED or not draw.video_id:
            return
        slot = self._slot_for(draw)
        try:
            result = await self.video_client.wait_for_result(
                api_key=slot.api_key,
                video_id=draw.video_id,
                poll_seconds=self.poll_seconds,
                timeout_seconds=self.poll_timeout_seconds,
            )
            draw.video_url = result.video_url
            draw.status = COMPLETED
        except Exception as exc:  # noqa: BLE001
            # Stay in CREATED on timeout: the task may still finish server-side
            # and a later resume can pick it up instead of burning a new draw.
            if isinstance(exc, TimeoutError):
                draw.error = f"poll timeout: {exc}"
            else:
                draw.status = FAILED
                draw.error = f"poll failed: {exc}"

    async def draw_shot(self, shot: ShotSpec, *, base_seed: int | None = None) -> GachaReport:
        shot.validate()
        planned = self._plan(shot, base_seed)
        for d in planned:
            self.ledger.upsert(d)

        # --- Phase 1: create everything, persist as soon as IDs are known ---
        await asyncio.gather(*(self._create_one(shot, d) for d in planned))
        self.ledger.save()

        # --- Phase 2: resolve ---
        await asyncio.gather(*(self._poll_one(d) for d in planned))
        self.ledger.save()

        report = GachaReport()
        for d in planned:
            if d.status == COMPLETED:
                report.completed.append(d)
            elif d.status == FAILED:
                report.failed.append(d)
            else:
                report.unresolved.append(d)
        return report

    async def resume(self) -> GachaReport:
        """Re-poll every draw still in CREATED after an interruption."""
        pending = [d for d in self.ledger.draws.values() if d.status == CREATED]
        await asyncio.gather(*(self._poll_one(d) for d in pending))
        self.ledger.save()
        report = GachaReport()
        for d in self.ledger.draws.values():
            if d.status == COMPLETED:
                report.completed.append(d)
            elif d.status == FAILED:
                report.failed.append(d)
            else:
                report.unresolved.append(d)
        return report
