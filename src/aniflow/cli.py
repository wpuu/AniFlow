from __future__ import annotations

import asyncio
import json
import shutil

import typer

from aniflow.agnes.http import AgnesHttpClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.agnes.video import AgnesVideoClient
from aniflow.agnes.vision import AgnesVisionJudge
from aniflow.config import get_settings
from aniflow.media.store import PublicMediaStore
from aniflow.pipeline.candidates import CandidateGenerator
from aniflow.pipeline.evaluate import CandidateEvaluator
from aniflow.pipeline.repair import PromptRepairer
from aniflow.pipeline.segment import SegmentPipeline

app = typer.Typer(no_args_is_help=True)


@app.command()
def doctor() -> None:
    """Check whether AniFlow has the minimum runtime configuration."""
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
            video = AgnesVideoClient(settings, http)
            judge = AgnesVisionJudge(settings, http)
            store = PublicMediaStore(settings)
            generator = CandidateGenerator(settings, key_pool, video)
            evaluator = CandidateEvaluator(key_pool=key_pool, judge=judge, media_store=store)
            repairer = PromptRepairer(settings, http)
            pipeline = SegmentPipeline(
                settings=settings,
                key_pool=key_pool,
                generator=generator,
                evaluator=evaluator,
                repairer=repairer,
            )
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


if __name__ == "__main__":
    app()
