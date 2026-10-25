"""Inspect a local finished MP4 using ffprobe; never call generation services.

Metadata can detect wrong display geometry, duration, and missing audio. It
CANNOT prove that the picture is visually upright or that claims are accurate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path


class ProbeError(RuntimeError):
    pass


def read_shotlist_contract(path: Path) -> dict:
    """Load a bounded, deterministic 9:16 shot timeline, not generation instructions.

    Only fields required to establish intended episode duration and frame-chain
    integrity are inspected. This does not replace AniFlow's FactPack gate.
    """
    try:
        path = path.expanduser()
        if not path.is_file() or path.stat().st_size > 1_048_576:
            raise ProbeError("Shotlist missing or exceeds 1 MiB limit")
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"Cannot read valid shotlist JSON ({type(exc).__name__})") from None
    if not isinstance(payload, dict):
        raise ProbeError("Shotlist root must be an object")
    episode_id = payload.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise ProbeError("Shotlist episode_id missing")
    if payload.get("aspect_ratio") != "9:16":
        raise ProbeError("Shotlist is not 9:16; this checker supports only 9:16")
    shots = payload.get("shots")
    if not isinstance(shots, list) or not shots or len(shots) > 100:
        raise ProbeError("Shotlist must contain 1–100 shots")

    seen = set()
    duration = 0
    ids = []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise ProbeError("Shotlist contains a non-object shot")
        shot_id = shot.get("shot_id")
        if not isinstance(shot_id, str) or not shot_id.strip() or shot_id in seen:
            raise ProbeError("Shot ID missing or duplicated")
        seen.add(shot_id)
        ids.append(shot_id)
        seconds = shot.get("seconds")
        if type(seconds) is not int or not 4 <= seconds <= 12:
            raise ProbeError("Shot duration must be an integer between 4 and 12 seconds")
        duration += seconds
        if not isinstance(shot.get("narration"), str):
            raise ProbeError("Shot narration is not text")
        inherits = shot.get("first_frame_from_previous", False)
        if type(inherits) is not bool:
            raise ProbeError("Invalid frame-inheritance flag")
        if inherits:
            if i == 0 or not isinstance(shots[i - 1].get("last_frame"), dict):
                raise ProbeError("Inherited first frame has no preceding last frame")
            if shot.get("first_frame") is not None:
                raise ProbeError("Shot cannot inherit and define a first frame")
        elif not isinstance(shot.get("first_frame"), dict):
            raise ProbeError("Shot requires a first frame or an explicit inheritance")

    return {
        "episode_id": episode_id.strip(),
        "shot_count": len(shots),
        "shot_ids": ids,
        "expected_duration_seconds": duration,
        "shotlist_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _rotation(stream: dict) -> int:
    """Best-effort display-matrix rotation; 0 when untagged."""
    tags = stream.get("tags") or {}
    side_data = stream.get("side_data_list") or []
    if not isinstance(tags, dict) or not isinstance(side_data, list):
        raise ProbeError("Malformed rotation metadata structure")
    rotation = tags.get("rotate")
    for item in side_data:
        if not isinstance(item, dict):
            raise ProbeError("Malformed rotation metadata entry")
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
                     min_short_side: int = 0, expected_seconds: float | None = None,
                     duration_tolerance: float = 0.75,
                     require_audio_coverage: bool = False) -> dict:
    """Reduce ffprobe JSON to non-sensitive QA evidence and fail closed."""
    if min_seconds <= 0 or max_seconds < min_seconds:
        raise ValueError("Invalid duration limits")
    if min_short_side < 0:
        raise ValueError("Invalid resolution threshold")
    if expected_ratio != "9:16":
        raise ValueError("Only explicit 9:16 portrait acceptance is supported")
    if not isinstance(data, dict) or not isinstance(data.get("streams"), list):
        raise ValueError("Malformed ffprobe stream metadata")
    if expected_seconds is not None and (
        isinstance(expected_seconds, bool) or not isinstance(expected_seconds, (int, float))
        or not math.isfinite(expected_seconds) or expected_seconds <= 0
    ):
        raise ValueError("Invalid expected episode duration")
    if not isinstance(duration_tolerance, (int, float)) or not math.isfinite(duration_tolerance) or duration_tolerance < 0:
        raise ValueError("Invalid episode duration tolerance")
    streams = data.get("streams")
    if any(not isinstance(s, dict) for s in streams):
        raise ValueError("Malformed ffprobe stream entry")
    if not isinstance(data.get("format"), dict):
        raise ValueError("Malformed ffprobe format metadata")
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    audio_present = bool(audios)
    blockers: list[str] = []
    width = height = rotated_width = rotated_height = rotation = None
    if len(videos) != 1:
        blockers.append("Expected exactly one video stream")
    else:
        video = videos[0]
        width, height = video.get("width"), video.get("height")
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
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
    if duration is not None and math.isfinite(duration) and expected_seconds is not None:
        if abs(duration - expected_seconds) > duration_tolerance:
            blockers.append("Final video duration differs from locked shotlist")

    audio_duration = None
    audio_start = None
    if require_audio_coverage:
        if len(audios) != 1:
            blockers.append("Expected exactly one audio stream for timeline acceptance")
        else:
            audio = audios[0]
            try:
                audio_duration = float(audio.get("duration"))
                audio_start = float(audio.get("start_time"))
            except (ValueError, TypeError):
                blockers.append("Audio stream duration/start metadata missing")
            else:
                if not all(math.isfinite(x) for x in (audio_duration, audio_start)) or audio_duration <= 0:
                    blockers.append("Invalid audio duration/start metadata")
                elif (audio_start < -0.25 or audio_start > 1.5 or
                      duration is None or audio_start + audio_duration < duration - duration_tolerance):
                    blockers.append("Audio stream does not cover the expected episode timeline")

    return {
        "result": "BLOCKED" if blockers else "METADATA_OK_HUMAN_QA_REQUIRED",
        "duration_seconds": round(duration, 3) if duration is not None and math.isfinite(duration) else None,
        "coded_dimensions": [width, height],
        "display_dimensions": [rotated_width, rotated_height],
        "rotation_degrees": rotation,
        "audio_present": audio_present,
        "audio_duration_seconds": round(audio_duration, 3) if audio_duration is not None and math.isfinite(audio_duration) else None,
        "expected_duration_seconds": expected_seconds,
        "duration_tolerance_seconds": duration_tolerance if expected_seconds is not None else None,
        "expected_ratio": expected_ratio,
        "blockers": blockers,
        "warnings": [
            "Metadata alone cannot detect sideways pixels or distorted subjects: manually watch the full clip.",
            "An audio stream does not prove audible speech; transcription and lip sync require review.",
            "Aggregate duration alone cannot prove every planned shot appears: review the full timeline.",
            "Scientific accuracy, character consistency, copyright and AI labels are not validated.",
        ],
    }


def inspect_file(path: Path, *, min_seconds: float, max_seconds: float,
                 require_audio: bool, min_short_side: int,
                 shotlist: Path | None = None, duration_tolerance: float = 0.75) -> dict:
    contract = read_shotlist_contract(shotlist) if shotlist is not None else None
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
    report = inspect_metadata(
        data, min_seconds=min_seconds, max_seconds=max_seconds,
        require_audio=(require_audio or contract is not None),
        min_short_side=min_short_side,
        expected_seconds=contract["expected_duration_seconds"] if contract else None,
        duration_tolerance=duration_tolerance,
        require_audio_coverage=contract is not None,
    )
    if contract is not None:
        report["shotlist_contract"] = contract
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
    parser.add_argument("--shotlist", type=Path, help="Lock a finished episode to the input shotlist JSON")
    parser.add_argument("--duration-tolerance", type=float, default=0.75)
    args = parser.parse_args(argv)
    lo, hi = (4, 12) if args.kind == "clip" else (30, 60)
    if args.min_seconds is not None:
        lo = args.min_seconds
    if args.max_seconds is not None:
        hi = args.max_seconds
    try:
        if args.shotlist is not None and args.kind != "episode":
            raise ProbeError("--shotlist requires --kind episode")
        report = inspect_file(
            args.video, min_seconds=lo, max_seconds=hi,
            require_audio=args.require_audio, min_short_side=args.min_short_side,
            shotlist=args.shotlist, duration_tolerance=args.duration_tolerance,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["result"] == "METADATA_OK_HUMAN_QA_REQUIRED" else 2
    except (ProbeError, ValueError) as exc:
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
