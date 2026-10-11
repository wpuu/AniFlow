"""Inspect a local finished MP4 using ffprobe; never call generation services.

Metadata can detect wrong display geometry, duration, and missing audio. It
CANNOT prove that the picture is visually upright or that claims are accurate.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path


class ProbeError(RuntimeError):
    pass


def _rotation(stream: dict) -> int:
    """Best-effort display-matrix rotation; 0 when untagged."""
    rotation = (stream.get("tags") or {}).get("rotate")
    for item in stream.get("side_data_list") or []:
        if item.get("rotation") is not None:
            rotation = item["rotation"]
            break
    try:
        degrees = float(rotation or 0)
    except (ValueError, TypeError):
        raise ProbeError("Malformed stream rotation metadata") from None
    if not math.isfinite(degrees):
        raise ProbeError("Non-finite rotation metadata")
    # Metadata occasionally returns -90, 270, etc.
    rounded = round(degrees)
    if abs(degrees - rounded) > 0.5 or rounded % 90 != 0:
        raise ProbeError("Unexpected non-right-angle display rotation")
    return rounded % 360


def inspect_metadata(data: dict, *, min_seconds: float = 4, max_seconds: float = 12,
                     require_audio: bool = False, expected_ratio: str = "9:16",
                     min_short_side: int = 0) -> dict:
    """Reduce ffprobe JSON to non-sensitive QA evidence and fail closed."""
    if min_seconds <= 0 or max_seconds < min_seconds:
        raise ValueError("Invalid duration limits")
    if min_short_side < 0:
        raise ValueError("Invalid resolution threshold")
    if expected_ratio != "9:16":
        raise ValueError("Only explicit 9:16 portrait acceptance is supported")
    streams = data.get("streams") or []
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audio_present = any(s.get("codec_type") == "audio" for s in streams)
    blockers: list[str] = []
    width = height = rotated_width = rotated_height = rotation = None
    if len(videos) != 1:
        blockers.append("Expected exactly one video stream")
    else:
        video = videos[0]
        width, height = video.get("width"), video.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            blockers.append("Invalid video dimensions")
        else:
            try:
                rotation = _rotation(video)
            except ProbeError as exc:
                blockers.append(str(exc))
            else:
                rotated_width, rotated_height = (height, width) if rotation in (90, 270) else (width, height)
                if rotated_width >= rotated_height:
                    blockers.append("Displayed geometry is not portrait 9:16")
                else:
                    ratio = rotated_width / rotated_height
                    if abs(ratio - 9 / 16) > 0.025:
                        blockers.append("Displayed geometry differs from 9:16")
                if min(rotated_width, rotated_height) < min_short_side:
                    blockers.append("Short side below specified resolution")

    raw_duration = (data.get("format") or {}).get("duration")
    try:
        duration = float(raw_duration)
    except (ValueError, TypeError):
        duration = None
    if duration is None or not math.isfinite(duration) or duration <= 0:
        blockers.append("Missing or invalid duration")
    elif not (min_seconds - 0.15 <= duration <= max_seconds + 0.15):
        blockers.append("Duration outside allowed range")
    if require_audio and not audio_present:
        blockers.append("Audio stream missing")

    return {
        "result": "BLOCKED" if blockers else "METADATA_OK_HUMAN_QA_REQUIRED",
        "duration_seconds": round(duration, 3) if duration is not None and math.isfinite(duration) else None,
        "coded_dimensions": [width, height],
        "display_dimensions": [rotated_width, rotated_height],
        "rotation_degrees": rotation,
        "audio_present": audio_present,
        "expected_ratio": expected_ratio,
        "blockers": blockers,
        "warnings": [
            "Metadata alone cannot detect sideways pixels or distorted subjects: manually watch the full clip.",
            "Audio transcription, scientific accuracy, character consistency, copyright and AI labels are not validated.",
        ],
    }


def inspect_file(path: Path, *, min_seconds: float, max_seconds: float,
                 require_audio: bool, min_short_side: int) -> dict:
    path = path.expanduser()
    if not path.is_file():
        raise ProbeError("Video file not found")
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(f"ffprobe not available ({type(exc).__name__})") from None
    if proc.returncode != 0:
        raise ProbeError("ffprobe could not inspect video (technical output suppressed)")
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        raise ProbeError("ffprobe returned malformed JSON") from None
    report = inspect_metadata(data, min_seconds=min_seconds,
                              max_seconds=max_seconds, require_audio=require_audio,
                              min_short_side=min_short_side)
    report["filename"] = path.name  # Avoid including full user home directory in reports.
    report["file_size_bytes"] = path.stat().st_size
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Local MP4 to inspect (not uploaded)")
    parser.add_argument("--kind", choices=("clip", "episode"), default="clip")
    parser.add_argument("--require-audio", action="store_true")
    parser.add_argument("--min-short-side", type=int, default=0)
    parser.add_argument("--min-seconds", type=float)
    parser.add_argument("--max-seconds", type=float)
    args = parser.parse_args(argv)
    lo, hi = (4, 12) if args.kind == "clip" else (30, 60)
    if args.min_seconds is not None:
        lo = args.min_seconds
    if args.max_seconds is not None:
        hi = args.max_seconds
    try:
        report = inspect_file(args.video, min_seconds=lo, max_seconds=hi,
                              require_audio=args.require_audio,
                              min_short_side=args.min_short_side)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["result"] == "METADATA_OK_HUMAN_QA_REQUIRED" else 2
    except (ProbeError, ValueError) as exc:
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
