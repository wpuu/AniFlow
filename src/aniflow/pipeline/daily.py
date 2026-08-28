from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from aniflow.agnes.http import AgnesHttpClient
from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.config import Settings
from aniflow.media.store import PublicMediaStore
from aniflow.pipeline.character import CharacterReferenceSet
from aniflow.pipeline.episode import EpisodePipeline
from aniflow.pipeline.ideas import IdeaGenerator, StoryIdea
from aniflow.pipeline.segment import SegmentPipeline
from aniflow.pipeline.storyboard import StoryboardPlanner


class DailyHistoryItem(BaseModel):
    episode_id: str
    created_at: str
    character_id: str
    style_key: str
    title: str
    premise: str
    completed: bool
    final_public_url: str | None = None
    ab_score: float | None = None
    bc_score: float | None = None
    ab_rounds: int = 0
    bc_rounds: int = 0


class DailyHistory(BaseModel):
    items: list[DailyHistoryItem] = Field(default_factory=list)


class DailyRunReport(BaseModel):
    run_id: str
    character_id: str
    style_key: str
    requested: int
    completed: int
    items: list[DailyHistoryItem] = Field(default_factory=list)


class DailyRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        key_pool: KeyPool,
        http: AgnesHttpClient,
        image_client: AgnesImageClient,
        segment_pipeline: SegmentPipeline,
        media_store: PublicMediaStore,
    ) -> None:
        self.settings = settings
        self.key_pool = key_pool
        self.http = http
        self.idea_generator = IdeaGenerator(settings, http)
        self.episode_pipeline = EpisodePipeline(
            settings=settings,
            key_pool=key_pool,
            storyboard_planner=StoryboardPlanner(settings, http),
            image_client=image_client,
            segment_pipeline=segment_pipeline,
            media_store=media_store,
        )

    async def run(
        self,
        *,
        character_id: str,
        style_key: str,
        count: int = 3,
        concurrency: int = 2,
        character_dir: Path = Path("data/characters"),
        history_path: Path = Path("data/daily/history.json"),
        report_dir: Path = Path("data/daily/runs"),
        output_root: Path = Path("output/daily"),
    ) -> DailyRunReport:
        if count < 1:
            raise ValueError("count must be at least 1")
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")

        profile = self._load_profile(character_dir, character_id, style_key)
        history = self._load_history(history_path)
        previous_titles = [item.title for item in history.items]
        idea_slot = await self.key_pool.next()
        batch = await self.idea_generator.generate(
            api_key=idea_slot.api_key,
            count=count,
            character_description=profile.bible.identity_prompt(),
            style_description=profile.style_description,
            previous_titles=previous_titles,
        )

        now = datetime.now(timezone.utc)
        run_id = now.strftime("%Y%m%dT%H%M%SZ")
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(index: int, idea: StoryIdea) -> DailyHistoryItem:
            async with semaphore:
                episode_id = (
                    f"{self._slug(character_id)}-{self._slug(style_key)}-"
                    f"{run_id}-{index + 1:02d}"
                )
                result = await self.episode_pipeline.run(
                    episode_id=episode_id,
                    idea=f"{idea.premise} Visual hook: {idea.visual_hook}",
                    character_description=profile.bible.identity_prompt(),
                    character_reference_urls=profile.urls,
                    output_dir=output_root / now.strftime("%Y-%m-%d"),
                    style=profile.style_description,
                )
                return DailyHistoryItem(
                    episode_id=episode_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    character_id=character_id,
                    style_key=style_key,
                    title=idea.title,
                    premise=idea.premise,
                    completed=result.completed,
                    final_public_url=result.final_public_url,
                    ab_score=(
                        result.segment_ab.selected.total
                        if result.segment_ab.selected is not None
                        else None
                    ),
                    bc_score=(
                        result.segment_bc.selected.total
                        if result.segment_bc.selected is not None
                        else None
                    ),
                    ab_rounds=len(result.segment_ab.rounds),
                    bc_rounds=len(result.segment_bc.rounds),
                )

        items = list(
            await asyncio.gather(
                *[run_one(index, idea) for index, idea in enumerate(batch.ideas)]
            )
        )
        history.items.extend(items)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            json.dumps(history.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        report = DailyRunReport(
            run_id=run_id,
            character_id=character_id,
            style_key=style_key,
            requested=count,
            completed=sum(1 for item in items if item.completed),
            items=items,
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / f"{run_id}.json").write_text(
            json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report

    @classmethod
    def _load_profile(
        cls,
        character_dir: Path,
        character_id: str,
        style_key: str,
    ) -> CharacterReferenceSet:
        path = character_dir / f"{cls._slug(character_id)}-{cls._slug(style_key)}.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing character style profile: {path}. Run `aniflow character` first."
            )
        return CharacterReferenceSet.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_history(path: Path) -> DailyHistory:
        if not path.is_file():
            return DailyHistory()
        return DailyHistory.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
        return slug or "item"
