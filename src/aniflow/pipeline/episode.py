from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.config import Settings
from aniflow.media.assemble import assemble_vertical_two_segments
from aniflow.media.images import persist_remote_image
from aniflow.media.store import PublicMediaStore
from aniflow.pipeline.keyframes import KeyframeGenerator, KeyframeSet
from aniflow.pipeline.segment import SegmentPipeline, SegmentRunResult
from aniflow.pipeline.storyboard import Storyboard3, StoryboardPlanner


@dataclass(slots=True)
class EpisodeRunResult:
    episode_id: str
    storyboard: Storyboard3
    keyframes: KeyframeSet
    segment_ab: SegmentRunResult
    segment_bc: SegmentRunResult
    final_local_path: str | None = None
    final_public_url: str | None = None

    @property
    def completed(self) -> bool:
        return self.segment_ab.selected is not None and self.segment_bc.selected is not None

    def as_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "completed": self.completed,
            "storyboard": self.storyboard.model_dump(),
            "keyframes": {
                "a": self.keyframes.frame_a_url,
                "b": self.keyframes.frame_b_url,
                "c": self.keyframes.frame_c_url,
            },
            "segment_ab": self.segment_ab.as_dict(),
            "segment_bc": self.segment_bc.as_dict(),
            "final_local_path": self.final_local_path,
            "final_public_url": self.final_public_url,
        }


class EpisodePipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        key_pool: KeyPool,
        storyboard_planner: StoryboardPlanner,
        image_client: AgnesImageClient,
        segment_pipeline: SegmentPipeline,
        media_store: PublicMediaStore | None = None,
    ) -> None:
        self.settings = settings
        self.key_pool = key_pool
        self.storyboard_planner = storyboard_planner
        self.keyframe_generator = KeyframeGenerator(key_pool, image_client)
        self.segment_pipeline = segment_pipeline
        self.media_store = media_store

    async def run(
        self,
        *,
        episode_id: str,
        idea: str,
        character_description: str,
        character_reference_urls: list[str],
        output_dir: Path,
        style: str = "handmade needle-felt miniature animation",
        candidates_per_round: int | None = None,
    ) -> EpisodeRunResult:
        planner_slot = await self.key_pool.next()
        storyboard = await self.storyboard_planner.create_three_frame_storyboard(
            api_key=planner_slot.api_key,
            idea=idea,
            character_description=character_description,
            style=style,
        )

        keyframes = await self.keyframe_generator.generate_three(
            storyboard=storyboard,
            character_reference_urls=character_reference_urls,
        )

        # Agnes image URLs may be temporary. Persist A/B/C before they are used as
        # video keyframes so generation, later review, and manifests share stable URLs.
        if self.media_store is not None:
            persisted = await asyncio.gather(
                persist_remote_image(
                    media_store=self.media_store,
                    source_url=keyframes.frame_a_url,
                    object_key_without_suffix=f"aniflow/episodes/{episode_id}/keyframes/a",
                ),
                persist_remote_image(
                    media_store=self.media_store,
                    source_url=keyframes.frame_b_url,
                    object_key_without_suffix=f"aniflow/episodes/{episode_id}/keyframes/b",
                ),
                persist_remote_image(
                    media_store=self.media_store,
                    source_url=keyframes.frame_c_url,
                    object_key_without_suffix=f"aniflow/episodes/{episode_id}/keyframes/c",
                ),
            )
            keyframes = KeyframeSet(
                frame_a_url=persisted[0],
                frame_b_url=persisted[1],
                frame_c_url=persisted[2],
            )

        segment_ab, segment_bc = await asyncio.gather(
            self.segment_pipeline.run(
                segment_id=f"{episode_id}-ab",
                prompt=storyboard.video_prompt_ab,
                story_action=storyboard.action_ab,
                first_frame_url=keyframes.frame_a_url,
                last_frame_url=keyframes.frame_b_url,
                candidates_per_round=candidates_per_round,
            ),
            self.segment_pipeline.run(
                segment_id=f"{episode_id}-bc",
                prompt=storyboard.video_prompt_bc,
                story_action=storyboard.action_bc,
                first_frame_url=keyframes.frame_b_url,
                last_frame_url=keyframes.frame_c_url,
                candidates_per_round=candidates_per_round,
            ),
        )

        result = EpisodeRunResult(
            episode_id=episode_id,
            storyboard=storyboard,
            keyframes=keyframes,
            segment_ab=segment_ab,
            segment_bc=segment_bc,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / f"{episode_id}.json"

        if result.completed:
            final_path = output_dir / f"{episode_id}.mp4"
            await assemble_vertical_two_segments(
                result.segment_ab.selected.video_url,
                result.segment_bc.selected.video_url,
                final_path,
            )
            result.final_local_path = str(final_path)
            if self.media_store is not None:
                result.final_public_url = await self.media_store.upload(
                    final_path,
                    f"aniflow/final/{episode_id}.mp4",
                )

        manifest_path.write_text(
            json.dumps(result.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result
