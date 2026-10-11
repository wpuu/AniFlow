"""AniFlow P0-006: fail-closed assembly of clips and shot-aligned voice assets.

This is an alternative to upstream creative-mode reauthoring. It DOES NOT create
Agnes tasks, edit upstream checkpoints, synthesize voice, or upload/publish media.
Default: --plan (no filesystem changes). Explicit --render creates a new file.
Requires approved shot MP4s and either one narration file or per-shot audio files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

_MAX_MANIFEST_BYTES = 1_048_576
_SHOT_ID = re.compile(r"[A-Za-z0-9_-]{1,20}\Z")


class AssemblyError(ValueError):
    """An unsafe or unverified input; no output should be produced."""


def _source_file(path: Path, *, extensions: set[str] | None = None) -> Path:
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise AssemblyError(f"Required regular file unavailable: {path.name}")
    if extensions is not None and path.suffix.lower() not in extensions:
        raise AssemblyError(f"Unexpected media extension: {path.name}")
    return path


def _read_manifest(path: Path) -> tuple[dict, str]:
    path = _source_file(path, extensions={".json"})
    if path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise AssemblyError("Manifest exceeds 1 MiB")
    raw = path.read_bytes()
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AssemblyError("Invalid manifest JSON") from None
    if not isinstance(parsed, dict):
        raise AssemblyError("Manifest root must be object")
    return parsed, hashlib.sha256(raw).hexdigest()


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _duration(value: object, *, label: str) -> float:
    try:
        d = float(value)
    except (ValueError, TypeError):
        raise AssemblyError(f"{label} duration missing") from None
    if not math.isfinite(d) or d <= 0:
        raise AssemblyError(f"{label} duration invalid")
    return d


def _probe(path: Path) -> dict:
    try:
        done = subprocess.run([
            "ffprobe", "-v", "error", "-of", "json", "-show_streams", "-show_format", str(path)
        ], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise AssemblyError("ffprobe unavailable or timed out") from None
    if done.returncode != 0 or len(done.stdout) > 3_000_000:
        raise AssemblyError(f"ffprobe rejected input {path.name}")
    try:
        value = json.loads(done.stdout)
    except json.JSONDecodeError:
        raise AssemblyError("ffprobe returned invalid JSON") from None
    if not isinstance(value, dict) or not isinstance(value.get("streams"), list):
        raise AssemblyError("ffprobe metadata shape invalid")
    return value


def _video_probe(path: Path, *, expected: int, width: int, height: int, tolerance: float) -> dict:
    data = _probe(path)
    streams = [s for s in data["streams"] if isinstance(s, dict) and s.get("codec_type") == "video"]
    if len(streams) != 1:
        raise AssemblyError(f"Expected one video stream: {path.name}")
    v = streams[0]
    if type(v.get("width")) is not int or type(v.get("height")) is not int:
        raise AssemblyError(f"Missing coded dimensions: {path.name}")
    if v["width"] != width or v["height"] != height:
        raise AssemblyError(f"Clip is not {width}x{height}: {path.name}")
    # Even 720x1280 container pixels can be sideways; mark any display transform unsafe.
    rot = (v.get("tags") or {}).get("rotate", 0)
    for item in v.get("side_data_list") or []:
        if isinstance(item, dict) and item.get("rotation") is not None:
            rot = item["rotation"]
            break
    try:
        r = float(rot or 0)
    except (ValueError, TypeError):
        raise AssemblyError(f"Invalid clip rotation: {path.name}") from None
    if not math.isfinite(r) or abs(r % 360) > 0.01:
        raise AssemblyError(f"Clip has display rotation metadata: {path.name}")
    fmt = data.get("format") or {}
    d = _duration(fmt.get("duration"), label="Clip")
    if abs(d - expected) > tolerance:
        raise AssemblyError(f"Clip duration differs from locked shotlist: {path.name}")
    return {"seconds": round(d, 3), "sha256": _hash_file(path)}


def _audio_probe(path: Path, *, expected: int, per_shot: bool = False) -> dict:
    data = _probe(path)
    tracks = [s for s in data["streams"] if isinstance(s, dict) and s.get("codec_type") == "audio"]
    if len(tracks) != 1:
        raise AssemblyError("Expected a single narration audio stream")
    fmt = data.get("format") or {}
    d = _duration(fmt.get("duration"), label="Narration")
    if per_shot:
        # Respect sentence boundaries: a long spoken line must not be silently
        # truncated to the shot length. 100ms covers small container rounding.
        if d < 0.35:
            raise AssemblyError("Per-shot narration is implausibly short")
        if d > expected + 0.10:
            raise AssemblyError("Per-shot narration exceeds its locked shot window")
    else:
        if d < max(1, expected * 0.30):
            raise AssemblyError("Narration unexpectedly short for full episode")
        if d > expected + 0.5:
            raise AssemblyError("Narration exceeds locked episode length")
    return {"seconds": round(d, 3), "sha256": _hash_file(path),
            "will_pad_with_silence": d < expected - 0.25}


def _content_contract(shotlist: Path, factpack: Path) -> dict:
    s, s_hash = _read_manifest(shotlist)
    p, p_hash = _read_manifest(factpack)
    eid = s.get("episode_id")
    if not isinstance(eid, str) or not _SHOT_ID.fullmatch(eid) or p.get("episode_id") != eid:
        raise AssemblyError("Episode ID differs or is invalid")
    if s.get("aspect_ratio") != "9:16":
        raise AssemblyError("Only locked 9:16 source manifests allowed")
    shots = s.get("shots")
    if not isinstance(shots, list) or not 1 <= len(shots) <= 30:
        raise AssemblyError("Expected 1 to 30 shot objects")
    seen: set[str] = set()
    schedule: list[dict] = []
    previous_end = None
    narration: list[str] = []
    for index, sh in enumerate(shots):
        if not isinstance(sh, dict):
            raise AssemblyError("Malformed shot")
        sid = sh.get("shot_id")
        if not isinstance(sid, str) or not _SHOT_ID.fullmatch(sid) or sid in seen:
            raise AssemblyError("Invalid or duplicate shot ID")
        seen.add(sid)
        secs = sh.get("seconds")
        if type(secs) is not int or not 4 <= secs <= 12:
            raise AssemblyError("Shot duration outside 4..12 seconds")
        if sh.get("first_frame_from_previous") is True:
            if index == 0 or previous_end is None or sh.get("first_frame") is not None:
                raise AssemblyError("Invalid inherited frame chain")
        elif not isinstance(sh.get("first_frame"), dict):
            raise AssemblyError("Missing initial frame")
        end = sh.get("last_frame")
        if end is not None and not isinstance(end, dict):
            raise AssemblyError("Invalid last frame")
        previous_end = end
        voice = sh.get("narration")
        if not isinstance(voice, str) or not voice.strip():
            raise AssemblyError("Missing shot narration")
        narration.append(voice)
        schedule.append({"id": sid, "seconds": secs, "filename": f"scene_{sid}.mp4"})
    for forbidden in p.get("forbidden_claims", []):
        if isinstance(forbidden, str) and forbidden.strip() and forbidden.strip() in "".join(narration):
            raise AssemblyError("Locked narration includes forbidden phrase")
    return {"episode_id": eid, "shotlist_sha256": s_hash, "factpack_sha256": p_hash,
            "shot_count": len(shots), "total_seconds": sum(x["seconds"] for x in schedule),
            "schedule": schedule}


def preflight(*, shotlist: Path, factpack: Path, clips_dir: Path,
              narration: Path | None = None, scene_audio_dir: Path | None = None,
              output: Path, tolerance: float = 0.3, width: int = 720, height: int = 1280,
              fixture_mode: bool = False) -> tuple[dict, list[Path], list[Path]]:
    """No writes; check all inputs and exact shot contract before encoding."""
    if (narration is None) == (scene_audio_dir is None):
        raise AssemblyError("Choose exactly one narration source: --narration OR --scene-audio-dir")
    if not math.isfinite(tolerance) or not (0 <= tolerance <= 0.5):
        raise AssemblyError("Clip duration tolerance must be between 0 and 0.5 seconds")
    if width * 16 != height * 9 or width < 16 or height < 16:
        raise AssemblyError("Output geometry must be integer 9:16")
    if (width, height) != (720, 1280) and not fixture_mode:
        raise AssemblyError("Production output must be 720x1280")
    contract = _content_contract(shotlist, factpack)
    clips_dir = Path(clips_dir)
    if clips_dir.is_symlink() or not clips_dir.is_dir():
        raise AssemblyError("Clips directory unavailable or symlink")
    output = Path(output).expanduser()
    if output.suffix.lower() != ".mp4" or output.is_symlink() or output.exists():
        raise AssemblyError("Output must be a new .mp4 path and must not already exist")
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise AssemblyError("Output parent must already exist and not be symlink")
    clips: list[Path] = []
    evidence = []
    for sh in contract["schedule"]:
        path = _source_file(clips_dir / sh["filename"], extensions={".mp4"})
        check = _video_probe(path, expected=sh["seconds"], width=width,
                             height=height, tolerance=tolerance)
        clips.append(path)
        evidence.append({"shot_id": sh["id"], "filename": path.name,
                         "planned_seconds": sh["seconds"], **check})
    if scene_audio_dir is not None:
        folder = Path(scene_audio_dir)
        if folder.is_symlink() or not folder.is_dir():
            raise AssemblyError("Per-shot narration folder missing or symlink")
        inputs: list[Path] = []
        parts: list[dict] = []
        for sh in contract["schedule"]:
            # Reject ambiguous duplicate formats for a given shot; never guess.
            options = [folder / f"narration_{sh['id']}{ext}"
                       for ext in (".wav", ".mp3", ".m4a", ".aac")]
            found = [p for p in options if p.exists() or p.is_symlink()]
            if len(found) != 1:
                raise AssemblyError(f"Expected exactly one narration for shot {sh['id']}")
            source = _source_file(found[0], extensions={".mp3", ".wav", ".m4a", ".aac"})
            info = _audio_probe(source, expected=sh["seconds"], per_shot=True)
            inputs.append(source)
            parts.append({"shot_id": sh["id"], "filename": source.name,
                          "window_seconds": sh["seconds"], **info})
        audio_evidence = {"mode": "per_shot", "shots": parts,
                          "total_recorded_seconds": round(sum(p["seconds"] for p in parts), 3),
                          "total_seconds": contract["total_seconds"],
                          "silence_is_padded_at_each_shot_end": True}
    else:
        audio_file = _source_file(narration, extensions={".mp3", ".wav", ".m4a", ".aac"})
        inputs = [audio_file]
        audio_evidence = {"mode": "continuous", **_audio_probe(audio_file, expected=contract["total_seconds"])}
    return ({**contract, "clips": evidence, "narration": audio_evidence,
             "result": "SOURCE_MEDIA_CHECKED_NOT_RENDERED",
             "warnings": ["Audio alignment is structural only; actual spoken words have not been transcribed or fact-checked.",
                          "Pixel orientation, character identity, and visual science require human viewing.",
                          "Subtitles, commercial music/voice rights and AI labeling are not added."]},
            clips, inputs)


def render(*, shotlist: Path, factpack: Path, clips_dir: Path,
           narration: Path | None = None, scene_audio_dir: Path | None = None,
           output: Path, tolerance: float = 0.3, width: int = 720, height: int = 1280,
           fps: int = 24, fixture_mode: bool = False, execute: bool = False) -> dict:
    if not 1 <= fps <= 60:
        raise AssemblyError("FPS must be in 1..60")
    report, clips, audio_files = preflight(
        shotlist=shotlist, factpack=factpack, clips_dir=clips_dir,
        narration=narration, scene_audio_dir=scene_audio_dir,
        output=output, tolerance=tolerance,
        width=width, height=height, fixture_mode=fixture_mode)
    report["output_filename"] = Path(output).name
    if not execute:
        report["result"] = "PLAN_ONLY_NO_CHANGES"
        return report
    # Generate into a private sibling and publish only after probing the candidate.
    with tempfile.TemporaryDirectory(prefix="aniflow-local-assemble-", dir=Path(output).parent) as temp:
        tmp = Path(temp) / "output.mp4"
        graph = []
        for i, sh in enumerate(report["schedule"]):
            graph.append(f"[{i}:v:0]trim=duration={sh['seconds']},setpts=PTS-STARTPTS,fps={fps},scale={width}:{height},setsar=1,format=yuv420p[v{i}]")
        video_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
        graph.append(f"{video_inputs}concat=n={len(clips)}:v=1:a=0[v]")
        if report["narration"]["mode"] == "per_shot":
            for i, sh in enumerate(report["schedule"]):
                graph.append(
                    f"[{len(clips)+i}:a:0]aresample=48000:async=1:first_pts=0,"
                    f"aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
                    f"atrim=duration={sh['seconds']},asetpts=PTS-STARTPTS[a{i}]"
                )
            audio_inputs = "".join(f"[a{i}]" for i in range(len(clips)))
            graph.append(f"{audio_inputs}concat=n={len(clips)}:v=0:a=1[a]")
        else:
            graph.append(
                f"[{len(clips)}:a:0]aresample=48000:async=1:first_pts=0,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
                f"atrim=duration={report['total_seconds']},asetpts=PTS-STARTPTS[a]"
            )
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n"]
        for clip in clips:
            cmd += ["-i", str(clip)]
        for audio_path in audio_files:
            cmd += ["-i", str(audio_path)]
        cmd += ["-filter_complex", ";".join(graph),
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                str(tmp)]
        try:
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise AssemblyError("Local ffmpeg assembly failed or timed out") from None
        if run.returncode != 0:
            raise AssemblyError("Local ffmpeg assembly failed; technical output withheld")
        final = _probe(tmp)
        videos = [s for s in final["streams"] if isinstance(s, dict) and s.get("codec_type") == "video"]
        audios = [s for s in final["streams"] if isinstance(s, dict) and s.get("codec_type") == "audio"]
        d = _duration((final.get("format") or {}).get("duration"), label="Final output")
        if len(videos) != 1 or len(audios) != 1 or abs(d - report["total_seconds"]) > 0.75:
            raise AssemblyError("Rendered MP4 failed final duration or audio/video check")
        if videos[0].get("width") != width or videos[0].get("height") != height:
            raise AssemblyError("Rendered MP4 geometry mismatch")
        if Path(output).exists():
            raise AssemblyError("Output appeared during rendering; refusing overwrite")
        # Source and destination share a filesystem; hardlink creation is atomic,
        # fails if the output exists and leaves no partially copied user file.
        try:
            os.link(tmp, output)
        except FileExistsError:
            raise AssemblyError("Output appeared during rendering; refusing overwrite") from None
        except OSError:
            raise AssemblyError("Could not atomically publish rendered file") from None
        report["result"] = "ASSEMBLED_MP4_HUMAN_QA_REQUIRED"
        report["output_sha256"] = _hash_file(Path(output))
        report["actual_seconds"] = round(d, 3)
        report["human_approved"] = False
        report["publish_ready"] = False
        return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shotlist", type=Path, required=True)
    ap.add_argument("--factpack", type=Path, required=True)
    ap.add_argument("--clips-dir", type=Path, required=True)
    audio_group = ap.add_mutually_exclusive_group(required=True)
    audio_group.add_argument("--narration", type=Path,
                             help="Legacy continuous narration; cannot enforce shot-level timing")
    audio_group.add_argument("--scene-audio-dir", type=Path,
                             help="Preferred: directory with narration_<shot-id>.wav/.mp3 per shot")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--render", action="store_true", help="Explicitly assemble local checked clips")
    args = ap.parse_args(argv)
    try:
        result = render(shotlist=args.shotlist, factpack=args.factpack,
                        clips_dir=args.clips_dir, narration=args.narration,
                        scene_audio_dir=args.scene_audio_dir,
                        output=args.output, execute=args.render)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AssemblyError, OSError) as exc:
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
