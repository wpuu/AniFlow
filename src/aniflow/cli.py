from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path

import httpx
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
        "frontend_ready": settings.frontend_ready,
        "frontend_index": str(settings.frontend_index_path),
        "capcut_runner_ready": settings.capcut_runner_ready,
        "capcut_default_ready": settings.capcut_ready,
        "capcut_seedream_model": settings.capcut_seedream_model or None,
        "bridge_url": f"http://{settings.aniflow_bridge_host}:{settings.aniflow_bridge_port}",
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
    }
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@app.command("bridge")
def run_bridge(
    host: str | None = typer.Option(None, help="Loopback host; defaults to ANIFLOW_BRIDGE_HOST"),
    port: int | None = typer.Option(None, min=1, max=65535, help="Loopback port"),
) -> None:
    """Start the private loopback API used by the AniFlow browser frontend."""
    settings = get_settings()
    bind_host = (host or settings.aniflow_bridge_host).strip()
    if bind_host not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter("AniFlow Bridge may only bind to loopback (127.0.0.1/localhost/::1)")
    bind_port = port or settings.aniflow_bridge_port

    import uvicorn

    uvicorn.run(
        "aniflow.bridge.app:app",
        host=bind_host,
        port=bind_port,
        reload=False,
        access_log=False,
    )


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


@app.command("queue-probe")
def queue_probe(
    rounds: int = typer.Option(3, min=1, help="发射轮数"),
    interval: float = typer.Option(20.0, min=1.0, help="每轮间隔秒数"),
    watch: bool = typer.Option(False, "--watch", help="持续挂机直到测出结论"),
    seconds: int = typer.Option(8, min=4, max=12, help="测试视频时长"),
    download: bool = typer.Option(True, help="抢到位后下载视频并检测是否自带音轨"),
    out_dir: Path = typer.Option(Path("output/queue-probe"), help="视频保存目录"),
) -> None:
    """探测 Agnes 视频队列是【按账户】还是【全平台共享】。

    用 text 模式发射，不需要图片、不需要 R2。只要 .env 里有 AGNES_API_KEYS 就能跑。
    """
    from aniflow.queue_probe import (
        CAPACITY_AVAILABLE,
        INCONCLUSIVE_SATURATED,
        NO_KEYS,
        PER_ACCOUNT,
        VERDICT_TEXT,
        decide,
        resolve_and_download,
        run_round,
    )

    settings = get_settings()
    keys = settings.api_keys
    line = "=" * 58

    typer.echo(line)
    typer.echo(" AniFlow 视频队列探测")
    typer.echo(line)
    if not keys:
        head, body = VERDICT_TEXT[NO_KEYS]
        typer.echo(f" 结论: {head}\n {body}")
        raise typer.Exit(code=1)

    typer.echo(f" 模型     : {settings.agnes_video_model}")
    typer.echo(f" 账户数   : {len(keys)}")
    typer.echo(f" 模式     : {'持续挂机' if watch else f'{rounds} 轮'}   间隔 {interval:g} 秒")
    typer.echo(f" 时长     : {seconds} 秒   画幅 {settings.aniflow_aspect_ratio}")
    typer.echo(line)

    async def _run() -> int:
        collected: list = []
        won: tuple[str, str] | None = None  # (api_key, video_id)

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            index = 0
            while True:
                index += 1
                rnd = await run_round(
                    client,
                    base_url=settings.agnes_v1_url,
                    keys=keys,
                    model=settings.agnes_video_model,
                    seconds=seconds,
                    aspect_ratio=settings.aniflow_aspect_ratio,
                    index=index,
                )
                collected.append(rnd)

                typer.echo(f"\n第 {index} 轮   {time.strftime('%H:%M:%S')}")
                for a in rnd.attempts:
                    if a.accepted:
                        typer.echo(f"   {a.account_label:<11} 已入队   {a.video_id}")
                        if won is None:
                            slot = keys[int(a.account_label.split('-')[1]) - 1]
                            won = (slot, a.video_id or "")
                    else:
                        reason = a.code or a.detail or f"HTTP {a.http_status}"
                        typer.echo(f"   {a.account_label:<11} 被拒     {reason}")
                ok, no = len(rnd.accepted), len(rnd.rejected)
                flag = "   <<< 混合结果，已可定论" if rnd.is_mixed else ""
                typer.echo(f"   小结: {ok} 成功 / {no} 被拒{flag}")

                verdict = decide(collected)
                done = verdict == PER_ACCOUNT or (not watch and index >= rounds)
                if done:
                    break
                await asyncio.sleep(interval)

            verdict = decide(collected)
            typer.echo("\n" + line)
            head, body = VERDICT_TEXT[verdict]
            typer.echo(f" 结论: {head}")
            typer.echo(f"  {body}")
            typer.echo(line)

            if won and download:
                api_key, video_id = won
                typer.echo(f"\n 抢到队列位，正在等待出片: {video_id}")
                typer.echo(" （顺便回答第二个问题：视频是否自带音轨）")
                info = await resolve_and_download(
                    client,
                    api_root=settings.agnes_api_root.rstrip("/"),
                    api_key=api_key,
                    video_id=video_id,
                    model=settings.agnes_video_model,
                    out_dir=out_dir,
                )
                typer.echo("")
                if info.get("ok"):
                    audio = info.get("has_audio")
                    audio_text = {True: "是 ✅", False: "否 ❌", None: "无法判断"}[audio]
                    typer.echo(f"   已保存   : {info['path']}")
                    typer.echo(f"   大小     : {info['bytes'] / 1024:.0f} KB")
                    typer.echo(f"   时长/画质: {info.get('seconds')}s / {info.get('size')}")
                    typer.echo(f"   自带音轨 : {audio_text}")
                    typer.echo("\n 请自己看一遍这条视频，确认毛毡风格在动态下是否稳定。")
                else:
                    typer.echo(f"   未能取回: {info.get('reason')}")

            return 0 if verdict in (PER_ACCOUNT, CAPACITY_AVAILABLE) else 2

    raise typer.Exit(code=asyncio.run(_run()))



@app.command("factcheck")
def factcheck(
    pack_file: Path = typer.Argument(..., help="Fact Pack 的 json 文件"),
    script_file: Path = typer.Argument(..., help="待审的脚本（纯文本）"),
) -> None:
    """发布前的事实闸门。生成成功不等于可以发布。

    退出码 0 表示可以发布，1 表示被拦下 —— 方便以后接进自动流程。
    """
    from aniflow.factpack import FactPack, gate

    pack = FactPack.model_validate_json(pack_file.read_text(encoding="utf-8"))
    report = gate(pack, script_file.read_text(encoding="utf-8"))
    typer.echo(report.render())
    if report.warnings and report.publishable:
        typer.echo("\n（有提醒但不阻断，自己判断。）")
    raise typer.Exit(code=0 if report.publishable else 1)


@app.command("shots")
def shots(
    shotlist_file: Path = typer.Argument(..., help="镜头表 json"),
    pack_file: Path = typer.Option(None, "--pack", help="一并做事实审查"),
    out: Path = typer.Option(None, "--out", help="把工单写到文件"),
) -> None:
    """把镜头表打印成人照着往界面里粘的工单。

    带 --pack 时，旁白里的每个数字也要能在事实包里找到出处。
    """
    from aniflow.factpack import FactPack
    from aniflow.shotlist import ShotList, check_episode, render_worksheet, validate_shotlist

    sl = ShotList.model_validate_json(shotlist_file.read_text(encoding="utf-8"))

    if pack_file:
        raw = json.loads(pack_file.read_text(encoding="utf-8"))
        raw.pop("_notes", None)
        report = check_episode(sl, FactPack.model_validate(raw))
    else:
        from aniflow.factpack import AuditReport
        report = AuditReport(episode_id=sl.episode_id, issues=validate_shotlist(sl))

    typer.echo(report.render())
    typer.echo("")
    if not report.publishable:
        typer.echo("先把上面的问题改掉，再出工单。")
        raise typer.Exit(code=1)

    sheet = render_worksheet(sl)
    if out:
        out.write_text(sheet, encoding="utf-8")
        typer.echo(f"工单已写入 {out}")
    else:
        typer.echo(sheet)


if __name__ == "__main__":
    app()

