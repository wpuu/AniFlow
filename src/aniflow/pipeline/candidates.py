from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from aniflow.agnes.key_pool import KeyPool
from aniflow.agnes.video import AgnesVideoClient
from aniflow.config import Settings


@dataclass(frozen=True, slots=True)
class GeneratedCandidate:
    candidate_id: str
    account_label: str
    video_id: str
    video_url: str
    seed: int | None


@dataclass(slots=True)
class CandidateBatch:
    candidates: list[GeneratedCandidate] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class CandidateGenerator:
    def __init__(
        self,
        settings: Settings,
        key_pool: KeyPool,
        video_client: AgnesVideoClient,
    ) -> None:
        self.settings = settings
        self.key_pool = key_pool
        self.video_client = video_client

    async def generate_segment(
        self,
        *,
        segment_id: str,
        prompt: str,
        first_frame_url: str,
        last_frame_url: str,
        count: int | None = None,
        base_seed: int | None = None,
    ) -> CandidateBatch:
        # Default policy: use at least one candidate from every configured Agnes account.
        # If ANIFLOW_CANDIDATES_PER_SEGMENT is larger, continue round-robin for more draws.
        target_count = count or max(
            self.settings.aniflow_candidates_per_segment,
            len(self.key_pool),
        )

        async def generate_one(index: int):
            slot = await self.key_pool.next()
            seed = base_seed + index if base_seed is not None else None
            task = await self.video_client.create_keyframe_task(
                api_key=slot.api_key,
                prompt=prompt,
                first_frame_url=first_frame_url,
                last_frame_url=last_frame_url,
                seed=seed,
            )
            result = await self.video_client.wait_for_result(
                api_key=slot.api_key,
                video_id=task.video_id,
            )
            return GeneratedCandidate(
                candidate_id=f"{segment_id}-c{index + 1}",
                account_label=slot.label,
                video_id=task.video_id,
                video_url=result.video_url or "",
                seed=seed,
            )

        results = await asyncio.gather(
            *(generate_one(index) for index in range(target_count)),
            return_exceptions=True,
        )
        batch = CandidateBatch()
        for index, result in enumerate(results):
            if isinstance(result, BaseException):
                batch.failures.append(f"{segment_id}-c{index + 1}: {type(result).__name__}: {result}")
            else:
                batch.candidates.append(result)
        return batch
