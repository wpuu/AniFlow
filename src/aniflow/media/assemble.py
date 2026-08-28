from __future__ import annotations

import asyncio
from pathlib import Path

from aniflow.media.ffmpeg import download_video


async def assemble_vertical_two_segments(
    first_video_url: str,
    second_video_url: str,
    output_path: Path,
) -> Path:
    """Download two Agnes clips and concatenate into an exact 720x1280 H.264 video.

    V0.1 intentionally strips generated audio. Sound design is a later independent stage.
    Re-encoding avoids concat failures caused by container/timestamp differences.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    first_path = output_path.parent / f".{output_path.stem}-ab.mp4"
    second_path = output_path.parent / f".{output_path.stem}-bc.mp4"

    await asyncio.gather(
        download_video(first_video_url, first_path),
        download_video(second_video_url, second_path),
    )

    filter_graph = (
        "[0:v]scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];"
        "[1:v]scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[outv]"
    )

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(first_path),
        "-i",
        str(second_path),
        "-filter_complex",
        filter_graph,
        "-map",
        "[outv]",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-y",
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    try:
        if process.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"ffmpeg assembly failed: {stderr.decode(errors='replace')}")
        return output_path
    finally:
        first_path.unlink(missing_ok=True)
        second_path.unlink(missing_ok=True)
