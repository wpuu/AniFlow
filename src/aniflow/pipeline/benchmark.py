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


class BenchmarkRow(BaseModel):
    style_key: str
    idea_index: int
    episode_id: str
    title: str
    premise: str
    completed: bool
    final_public_url: str | None = None
    ab_score: float | None = None
    bc_score: float | None = None
    ab_rounds: int = 0
    bc_rounds: int = 0
    final_qa_total: float | None = None
    final_qa_advisory_pass: bool | None = None
    final_qa_error: str | None = None


class StyleSummary(BaseModel):
    style_key: str
    attempted: int
    completed: int
    completion_rate: float
    mean_ab_score: float | None = None
    mean_bc_score: float | None = None
    mean_rounds: float | None = None
    mean_final_qa_score: float | None = None
    final_qa_advisory_rate: float | None = None


class BenchmarkReport(BaseModel):
    run_id: str
    character_id: str
    created_at: str
    per_style_target: int
    shared_ideas: list[StoryIdea] = Field(default_factory=list)
    rows: list[BenchmarkRow] = Field(default_factory=list)
    summaries: list[StyleSummary] = Field(default_factory=list)


class HumanCalibrationRow(BaseModel):
    episode_id: str
    style_key: str
    title: str
    final_public_url: str | None = None
    machine_ab_score: float | None = None
    machine_bc_score: float | None = None
    machine_final_qa_score: float | None = None
    machine_final_qa_pass: bool | None = None
    human_usable: bool | None = None
    issue_identity: bool = False
    issue_anatomy: bool = False
    issue_background: bool = False
    issue_seam: bool = False
    issue_motion: bool = False
    issue_story: bool = False
    issue_visual_appeal: bool = False
    notes: str = ""


class HumanCalibrationSheet(BaseModel):
    run_id: str
    instructions: str = (
        "Review every final_public_url. Set human_usable true/false and mark only visible issue flags. "
        "Do not change machine scores. This first sheet calibrates AniFlow QA thresholds."
    )
    rows: list[HumanCalibrationRow] = Field(default_factory=list)


class BenchmarkRunner:
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
        style_keys: list[str],
        per_style: int = 10,
        character_dir: Path = Path("data/characters"),
        output_root: Path = Path("output/benchmarks"),
        report_dir: Path = Path("data/benchmarks"),
        calibration_dir: Path = Path("data/calibration"),
        concurrency: int = 2,
    ) -> BenchmarkReport:
        if per_style < 1:
            raise ValueError("per_style must be at least 1")
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if not style_keys:
            raise ValueError("At least one style key is required")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rows: list[BenchmarkRow] = []
        semaphore = asyncio.Semaphore(concurrency)

        profiles = {
            style_key: self._load_profile(character_dir, character_id, style_key)
            for style_key in style_keys
        }
        canonical_profile = profiles[style_keys[0]]
        idea_slot = await self.key_pool.next()
        batch = await self.idea_generator.generate(
            api_key=idea_slot.api_key,
            count=per_style,
            character_description=canonical_profile.bible.identity_prompt(),
            style_description=(
                "handcrafted miniature animation; every story must be equally suitable for needle-felt, "
                "clay stop-motion, and miniature toy-world rendering"
            ),
        )

        for style_key in style_keys:
            profile = profiles[style_key]

            async def run_one(index: int, idea: StoryIdea) -> BenchmarkRow:
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
                        output_dir=output_root / run_id / style_key,
                        style=profile.style_description,
                    )
                    return BenchmarkRow(
                        style_key=style_key,
                        idea_index=index + 1,
                        episode_id=episode_id,
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
                        final_qa_total=(result.final_qa.total if result.final_qa is not None else None),
                        final_qa_advisory_pass=(
                            result.final_qa.advisory_pass if result.final_qa is not None else None
                        ),
                        final_qa_error=result.final_qa_error,
                    )

            style_rows = await asyncio.gather(
                *[run_one(index, idea) for index, idea in enumerate(batch.ideas)]
            )
            rows.extend(style_rows)

        report = BenchmarkReport(
            run_id=run_id,
            character_id=character_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            per_style_target=per_style,
            shared_ideas=batch.ideas,
            rows=rows,
            summaries=self._summaries(rows, style_keys),
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / f"{run_id}.json").write_text(
            json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_calibration_sheet(report, calibration_dir / f"{run_id}.json")
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
    def _summaries(rows: list[BenchmarkRow], style_keys: list[str]) -> list[StyleSummary]:
        result: list[StyleSummary] = []
        for style_key in style_keys:
            subset = [row for row in rows if row.style_key == style_key]
            completed = [row for row in subset if row.completed]
            ab_scores = [row.ab_score for row in completed if row.ab_score is not None]
            bc_scores = [row.bc_score for row in completed if row.bc_score is not None]
            final_scores = [
                row.final_qa_total for row in completed if row.final_qa_total is not None
            ]
            final_passes = [
                row.final_qa_advisory_pass
                for row in completed
                if row.final_qa_advisory_pass is not None
            ]
            round_values = [
                (row.ab_rounds + row.bc_rounds) / 2
                for row in subset
                if row.ab_rounds or row.bc_rounds
            ]
            result.append(
                StyleSummary(
                    style_key=style_key,
                    attempted=len(subset),
                    completed=len(completed),
                    completion_rate=round(len(completed) / len(subset), 4) if subset else 0.0,
                    mean_ab_score=BenchmarkRunner._mean(ab_scores),
                    mean_bc_score=BenchmarkRunner._mean(bc_scores),
                    mean_rounds=BenchmarkRunner._mean(round_values),
                    mean_final_qa_score=BenchmarkRunner._mean(final_scores),
                    final_qa_advisory_rate=(
                        round(sum(bool(value) for value in final_passes) / len(final_passes), 4)
                        if final_passes
                        else None
                    ),
                )
            )
        return result

    @staticmethod
    def _write_calibration_sheet(report: BenchmarkReport, path: Path) -> None:
        sheet = HumanCalibrationSheet(
            run_id=report.run_id,
            rows=[
                HumanCalibrationRow(
                    episode_id=row.episode_id,
                    style_key=row.style_key,
                    title=row.title,
                    final_public_url=row.final_public_url,
                    machine_ab_score=row.ab_score,
                    machine_bc_score=row.bc_score,
                    machine_final_qa_score=row.final_qa_total,
                    machine_final_qa_pass=row.final_qa_advisory_pass,
                )
                for row in report.rows
            ],
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(sheet.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
        return slug or "item"
