from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import typer

from aniflow.agnes.http import AgnesHttpClient
from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.agnes.video import AgnesVideoClient
from aniflow.agnes.vision import AgnesVisionJudge
from aniflow.config import get_settings
from aniflow.media.store import PublicMediaStore
from aniflow.pipeline.benchmark import BenchmarkRunner
from aniflow.pipeline.candidates import CandidateGenerator
from aniflow.pipeline.character import CharacterBuilder
from aniflow.pipeline.daily import DailyRunner
from aniflow.pipeline.episode import EpisodePipeline
from aniflow.pipeline.evaluate import CandidateEvaluator
from aniflow.pipeline.repair import PromptRepairer
from aniflow.pipeline.segment import SegmentPipeline
from aniflow.pipeline.storyboard import StoryboardPlanner
from aniflow.preflight import run_preflight

app = typer.Typer(no_args_is_help=True)


@app.command()
def doctor() -> None:
    """Check whether AniFlow has the minimum local runtime configuration."""
    settings = get_settings()
    report = {
        "agnes_accounts": len(settings.api_keys),
        "agnes_text_model": settings.agnes_text_model,
        "agnes_image_model": settings.agnes_image_model,
        "agnes_video_model": settings.agnes_video_model,
        "aspect_ratio": settings.aniflow_aspect_ratio,
        "video_seconds": settings.aniflow_video_seconds,
        "s3_media_ready": settings.s3_ready,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
    }
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@app.command("preflight")
def preflight() -> None:
    """Verify every Agnes account and public media upload/read/delete before generation."""

    async def _run() -> dict:
        settings = get_settings()
        if not settings.api_keys:
            raise RuntimeError("AGNES_API_KEYS is empty")
        if not settings.s3_ready:
            raise RuntimeError("S3/R2 media storage is not fully configured")

        http = AgnesHttpClient()
        try:
            store = PublicMediaStore(settings)
            report = await run_preflight(settings=settings, http=http, media_store=store)
            return report.model_dump() | {"ok": report.ok}
        finally:
            await http.aclose()

    report = asyncio.run(_run())
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise typer.Exit(code=1)


def _build_segment_pipeline(settings, key_pool, http, store) -> SegmentPipeline:
    video = AgnesVideoClient(settings, http)
    judge = AgnesVisionJudge(settings, http)
    generator = CandidateGenerator(settings, key_pool, video)
    evaluator = CandidateEvaluator(key_pool=key_pool, judge=judge, media_store=store)
    repairer = PromptRepairer(settings, http)
    return SegmentPipeline(
        settings=settings,
        key_pool=key_pool,
        generator=generator,
        evaluator=evaluator,
        repairer=repairer,
    )


@app.command("character")
def build_character(
    character_id: str = typer.Option(..., help="Stable ID, e.g. filo"),
    name: str = typer.Option(..., help="Display name"),
    description: str = typer.Option(..., help="Core semantic character description"),
    style: list[str] | None = typer.Option(
        None,
        "--style",
        help="Style preset; repeat for multiple. Defaults to felt, clay, toy.",
    ),
) -> None:
    """Create one shared identity anchor and persistent style-specific reference sets."""

    async def _run() -> dict:
        settings = get_settings()
        if not settings.api_keys:
            raise RuntimeError("AGNES_API_KEYS is empty")
        key_pool = KeyPool(settings.api_keys)
        http = AgnesHttpClient()
        try:
            store = PublicMediaStore(settings)
            image_client = AgnesImageClient(settings, http)
            builder = CharacterBuilder(
                settings=settings,
                key_pool=key_pool,
                http=http,
                image_client=image_client,
                media_store=store,
            )
            bible = await builder.create_bible(
                character_id=character_id,
                display_name=name,
                description=description,
            )
            identity_anchor_url = await builder.build_identity_anchor(bible=bible)
            style_keys = style or ["felt", "clay", "toy"]
            reference_sets = await asyncio.gather(
                *[
                    builder.build_reference_set(
                        bible=bible,
                        style_key=style_key,
                        identity_anchor_url=identity_anchor_url,
                    )
                    for style_key in style_keys
                ]
            )
            return {
                "bible": bible.model_dump(),
                "identity_anchor_url": identity_anchor_url,
                "reference_sets": [item.model_dump() for item in reference_sets],
            }
        finally:
            await http.aclose()

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@app.command("segment")
def run_segment(
    segment_id: str = typer.Option(..., help="Stable ID, e.g. ep001-ab"),
    first_frame_url: str = typer.Option(...),
    last_frame_url: str = typer.Option(...),
    prompt: str = typer.Option(..., help="Agnes video motion/camera prompt"),
    story_action: str = typer.Option(..., help="What should visibly happen in this segment"),
    candidates: int | None = typer.Option(None, min=1),
) -> None:
    """Run multi-account generation -> visual judging -> prompt repair for one segment."""

    async def _run() -> dict:
        settings = get_settings()
        if not settings.api_keys:
            raise RuntimeError("AGNES_API_KEYS is empty")
        key_pool = KeyPool(settings.api_keys)
        http = AgnesHttpClient()
        try:
            store = PublicMediaStore(settings)
            pipeline = _build_segment_pipeline(settings, key_pool, http, store)
            result = await pipeline.run(
                segment_id=segment_id,
                prompt=prompt,
                story_action=story_action,
                first_frame_url=first_frame_url,
                last_frame_url=last_frame_url,
                candidates_per_round=candidates,
            )
            return result.as_dict()
        finally:
            await http.aclose()

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@app.command("episode")
def run_episode(
    episode_id: str = typer.Option(..., help="Stable ID, e.g. felt-0001"),
    idea: str = typer.Option(..., help="One-sentence story idea"),
    character_description: str = typer.Option(..., help="Fixed character bible summary"),
    character_ref: list[str] = typer.Option(
        ...,
        "--character-ref",
        help="Public character reference URL; repeat this option for multiple references",
    ),
    style: str = typer.Option("handmade needle-felt miniature animation"),
    candidates: int | None = typer.Option(None, min=1),
    output_dir: Path = typer.Option(Path("output")),
) -> None:
    """Create a complete 10-second A->B->C vertical episode."""

    async def _run() -> dict:
        settings = get_settings()
        if not settings.api_keys:
            raise RuntimeError("AGNES_API_KEYS is empty")
        if not character_ref:
            raise RuntimeError("At least one --character-ref URL is required")
        key_pool = KeyPool(settings.api_keys)
        http = AgnesHttpClient()
        try:
            store = PublicMediaStore(settings)
            segment_pipeline = _build_segment_pipeline(settings, key_pool, http, store)
            episode_pipeline = EpisodePipeline(
                settings=settings,
                key_pool=key_pool,
                storyboard_planner=StoryboardPlanner(settings, http),
                image_client=AgnesImageClient(settings, http),
                segment_pipeline=segment_pipeline,
                media_store=store,
            )
            result = await episode_pipeline.run(
                episode_id=episode_id,
                idea=idea,
                character_description=character_description,
                character_reference_urls=character_ref,
                output_dir=output_dir,
                style=style,
                candidates_per_round=candidates,
            )
            return result.as_dict()
        finally:
            await http.aclose()

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@app.command("benchmark")
def run_benchmark(
    character_id: str = typer.Option(..., help="Character ID previously created by `aniflow character`"),
    style: list[str] | None = typer.Option(
        None,
        "--style",
        help="Styles to compare; repeat this option. Defaults to felt, clay, toy.",
    ),
    per_style: int = typer.Option(10, min=1, help="Shared story count per style"),
    concurrency: int = typer.Option(2, min=1, max=8),
) -> None:
    """Run the same story set across multiple visual styles for fair comparison."""

    async def _run() -> dict:
        settings = get_settings()
        if not settings.api_keys:
            raise RuntimeError("AGNES_API_KEYS is empty")
        key_pool = KeyPool(settings.api_keys)
        http = AgnesHttpClient()
        try:
            store = PublicMediaStore(settings)
            image_client = AgnesImageClient(settings, http)
            segment_pipeline = _build_segment_pipeline(settings, key_pool, http, store)
            runner = BenchmarkRunner(
                settings=settings,
                key_pool=key_pool,
                http=http,
                image_client=image_client,
                segment_pipeline=segment_pipeline,
                media_store=store,
            )
            report = await runner.run(
                character_id=character_id,
                style_keys=style or ["felt", "clay", "toy"],
                per_style=per_style,
                concurrency=concurrency,
            )
            return report.model_dump()
        finally:
            await http.aclose()

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@app.command("daily")
def run_daily(
    character_id: str = typer.Option(..., help="Character ID previously created by `aniflow character`"),
    style: str = typer.Option(..., help="Chosen production style, e.g. felt"),
    count: int = typer.Option(3, min=1, max=20),
    concurrency: int = typer.Option(2, min=1, max=8),
) -> None:
    """Generate today's non-repeating episode batch and persist private history."""

    async def _run() -> dict:
        settings = get_settings()
        if not settings.api_keys:
            raise RuntimeError("AGNES_API_KEYS is empty")
        key_pool = KeyPool(settings.api_keys)
        http = AgnesHttpClient()
        try:
            store = PublicMediaStore(settings)
            image_client = AgnesImageClient(settings, http)
            segment_pipeline = _build_segment_pipeline(settings, key_pool, http, store)
            runner = DailyRunner(
                settings=settings,
                key_pool=key_pool,
                http=http,
                image_client=image_client,
                segment_pipeline=segment_pipeline,
                media_store=store,
            )
            report = await runner.run(
                character_id=character_id,
                style_key=style,
                count=count,
                concurrency=concurrency,
            )
            return report.model_dump()
        finally:
            await http.aclose()

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
