from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from aniflow.agnes.key_pool import KeyPool
from aniflow.agnes.vision import AgnesVisionJudge
from aniflow.media.ffmpeg import download_video, extract_sample_frames
from aniflow.media.store import PublicMediaStore
from aniflow.models import CandidateEvaluation
from aniflow.pipeline.candidates import GeneratedCandidate


class CandidateEvaluator:
    def __init__(
        self,
        *,
        key_pool: KeyPool,
        judge: AgnesVisionJudge,
        media_store: PublicMediaStore,
    ) -> None:
        self.key_pool = key_pool
        self.judge = judge
        self.media_store = media_store

    async def evaluate_one(
        self,
        *,
        job_id: str,
        candidate: GeneratedCandidate,
        first_frame_url: str,
        last_frame_url: str,
        story_action: str,
    ) -> CandidateEvaluation:
        slot = await self.key_pool.next()
        with tempfile.TemporaryDirectory(prefix="aniflow-") as tmp:
            root = Path(tmp)
            video_path = await download_video(candidate.video_url, root / "candidate.mp4")
            frame_paths = await extract_sample_frames(video_path, root / "frames")
            frame_urls = await asyncio.gather(
                *[
                    self.media_store.upload(
                        path,
                        f"aniflow/tmp/{job_id}/{candidate.candidate_id}/{path.name}",
                    )
                    for path in frame_paths
                ]
            )
            scores = await self.judge.judge_three_passes(
                api_key=slot.api_key,
                first_frame_url=first_frame_url,
                last_frame_url=last_frame_url,
                sampled_frame_urls=list(frame_urls),
                story_action=story_action,
            )
        return CandidateEvaluation(
            candidate_id=candidate.candidate_id,
            video_url=candidate.video_url,
            scores=scores,
        )

    async def evaluate_batch(
        self,
        *,
        job_id: str,
        candidates: list[GeneratedCandidate],
        first_frame_url: str,
        last_frame_url: str,
        story_action: str,
    ) -> tuple[list[CandidateEvaluation], list[str]]:
        results = await asyncio.gather(
            *[
                self.evaluate_one(
                    job_id=job_id,
                    candidate=candidate,
                    first_frame_url=first_frame_url,
                    last_frame_url=last_frame_url,
                    story_action=story_action,
                )
                for candidate in candidates
            ],
            return_exceptions=True,
        )
        evaluations: list[CandidateEvaluation] = []
        failures: list[str] = []
        for candidate, result in zip(candidates, results, strict=True):
            if isinstance(result, BaseException):
                failures.append(
                    f"{candidate.candidate_id}: {type(result).__name__}: {result}"
                )
            else:
                evaluations.append(result)
        evaluations.sort(key=lambda item: item.total, reverse=True)
        return evaluations, failures
