from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx


async def download_video(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
    return destination


async def probe_duration(video_path: Path) -> float:
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode(errors='replace')}")
    payload = json.loads(stdout.decode())
    return float(payload["format"]["duration"])


async def extract_sample_frames(
    video_path: Path,
    output_dir: Path,
    fractions: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = await probe_duration(video_path)
    if duration <= 0:
        raise ValueError("Video duration must be positive")

    # Avoid requesting a timestamp exactly beyond the final decodable frame.
    last_safe = max(0.0, duration - 0.05)
    results: list[Path] = []
    for index, fraction in enumerate(fractions):
        timestamp = min(last_safe, max(0.0, duration * fraction))
        output_path = output_dir / f"frame-{index:02d}.jpg"
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"ffmpeg frame extraction failed: {stderr.decode(errors='replace')}")
        results.append(output_path)
    return results
