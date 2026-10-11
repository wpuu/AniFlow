"""Offline MYCL-style shotlist export and upstream creative checkpoint guard.

No API requests, no upstream task mutation, no secret access. Tested against the
observed Agnes Video Generator v7.1.0 creative-task *file shapes*, not its runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

MAX_JSON = 1024 * 1024
EXPECTED_PAUSE = "step_script"


class ContractError(ValueError):
    """Fail-closed input or checkpoint error."""


def _read_json(path: Path) -> tuple[dict | list, str]:
    if not path.is_file() or path.is_symlink():
        raise ContractError(f"Required JSON file missing or symlink: {path.name}")
    if path.stat().st_size > MAX_JSON:
        raise ContractError(f"JSON file larger than 1 MiB: {path.name}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ContractError(f"Unreadable JSON: {path.name}") from None
    return value, hashlib.sha256(raw).hexdigest()


def _nonnull_str(v: object, name: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ContractError(f"Missing/invalid {name}")
    return v.strip()


def _frame_description(value: dict | None) -> str:
    if not isinstance(value, dict):
        return ""
    return "; ".join(v.strip() for k in ("composition", "subject_state", "environment")
                     if isinstance((v := value.get(k)), str) and v.strip())


def lock_contract(shotlist_path: Path, factpack_path: Path) -> dict:
    """Prepare the *target* for manual review; never claim it is already imported."""
    data, shot_hash = _read_json(shotlist_path)
    facts, fact_hash = _read_json(factpack_path)
    if not isinstance(data, dict) or not isinstance(facts, dict):
        raise ContractError("Shotlist and factpack roots must be JSON objects")
    eid = _nonnull_str(data.get("episode_id"), "episode_id")
    if facts.get("episode_id") != eid:
        raise ContractError("Factpack and shotlist episode_id mismatch")
    if data.get("aspect_ratio") != "9:16":
        raise ContractError("Only 9:16 locked episodes are supported")
    style = _nonnull_str(data.get("style"), "style")
    character = _nonnull_str(data.get("character"), "character")
    shots = data.get("shots")
    if not isinstance(shots, list) or not 1 <= len(shots) <= 30:
        raise ContractError("Shot count must be 1..30")

    prompts: list[str] = []
    durations: list[int] = []
    narration_lines: list[str] = []
    seen: set[str] = set()
    previous_end: dict | None = None
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise ContractError("Non-object shot entry")
        sid = _nonnull_str(shot.get("shot_id"), "shot_id")
        if sid in seen:
            raise ContractError("Duplicate shot_id")
        seen.add(sid)
        length = shot.get("seconds")
        if type(length) is not int or not 4 <= length <= 12:
            raise ContractError(f"Shot {sid} must have 4..12 integer seconds")
        inherit = shot.get("first_frame_from_previous") is True
        first = shot.get("first_frame")
        if inherit:
            if i == 0 or previous_end is None or first is not None:
                raise ContractError(f"Shot {sid} has broken/ambiguous first-frame inheritance")
            first = previous_end
        elif not isinstance(first, dict):
            raise ContractError(f"Shot {sid} has no independent first-frame")
        end = shot.get("last_frame")
        if end is not None and not isinstance(end, dict):
            raise ContractError(f"Shot {sid} has malformed last-frame")
        who = shot.get("character_override", character)
        if not isinstance(who, str):
            raise ContractError(f"Shot {sid} has malformed character_override")
        motion = _nonnull_str(shot.get("motion"), f"shot {sid} motion")
        narration = _nonnull_str(shot.get("narration"), f"shot {sid} narration")
        camera = shot.get("camera") or ""
        if not isinstance(camera, str):
            raise ContractError(f"Shot {sid} has invalid camera")
        # List[str] is the v7.1.0 creative pipeline's script.json shape.
        fields = [style, who.strip(), _frame_description(first), motion, camera.strip(),
                  _frame_description(end)]
        prompt = ". ".join(x for x in fields if x)
        prompts.append(prompt)
        narration_lines.append(narration)
        durations.append(length)
        previous_end = end

    locked_narration = "".join(narration_lines)
    for phrase in facts.get("forbidden_claims", []):
        if isinstance(phrase, str) and phrase.strip() and phrase.strip() in locked_narration:
            raise ContractError("Locked narration contains a forbidden Fact Pack phrase")

    return {
        "episode_id": eid,
        "shotlist_sha256": shot_hash,
        "factpack_sha256": fact_hash,
        "scene_count": len(shots),
        "scene_durations": durations,
        "expected_seconds": sum(durations),
        "scene_prompts": prompts,
        "locked_narration": locked_narration,
        "form_fields": {
            "duration_source": "manual",
            "scene_count": len(shots),
            "uniform_duration": False,
            "scene_durations_json": json.dumps(durations, separators=(",", ":")),
            "video_width": 720,
            "video_height": 1280,
            "execution_mode": "manual",
            "pause_points": json.dumps([EXPECTED_PAUSE]),
            "audio_enabled": True,
            "subtitle_enabled": True,
        },
        "compatibility": "v7.1.0 creative checkpoint file shapes; live runtime not tested",
    }


def _norm_narration(value: str) -> str:
    """Ignore whitespace layout, not punctuation or numbers."""
    return re.sub(r"\s+", "", value)


def inspect_checkpoint(contract: dict, task_dir: Path) -> dict:
    """Read-only guard. No HTTP, task edits, or claims about rendered results."""
    task_dir = Path(task_dir)
    state, _ = _read_json(task_dir / "task_state.json")
    script, _ = _read_json(task_dir / "script.json")
    blockers: list[str] = []
    if not isinstance(state, dict):
        raise ContractError("task_state.json must be an object")
    if state.get("task_type") != "creative":
        blockers.append("Upstream task is not creative mode")
    if state.get("duration_source") != "manual":
        blockers.append("Scene duration_source is not manual")
    if state.get("scene_count") != contract["scene_count"]:
        blockers.append("Upstream scene_count differs from shotlist")
    if state.get("scene_durations") != contract["scene_durations"]:
        blockers.append("Upstream scene_durations differ from shotlist")
    scenes = state.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != contract["scene_count"]:
        blockers.append("Persisted scene objects count differs from shotlist")
    elif any(not isinstance(x, dict) or type(x.get("duration")) is not int or
             x["duration"] != contract["scene_durations"][i]
             for i, x in enumerate(scenes)):
        blockers.append("Persisted scene object durations differ from shotlist")
    cfg = state.get("manual_config")
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True or \
            cfg.get("current_checkpoint") != EXPECTED_PAUSE:
        blockers.append("Not paused at the official step_script manual checkpoint")
    if state.get("step_video_generation") != "pending":
        blockers.append("Video generation has already started or has unknown status")
    if state.get("step_audio") != "pending":
        blockers.append("Audio generation has already started or has unknown status")
    if not isinstance(script, list) or not all(isinstance(x, str) for x in script):
        blockers.append("Upstream script.json is not the expected List[str] shape")
    elif script != contract["scene_prompts"]:
        blockers.append("Upstream scene prompts differ from locked AniFlow prompts")
    narrations = state.get("narrations")
    if not isinstance(narrations, list) or len(narrations) != 1 or not isinstance(narrations[0], str):
        blockers.append("Expected exactly one upstream continuous narration")
    elif _norm_narration(narrations[0]) != _norm_narration(contract["locked_narration"]):
        blockers.append("Upstream narration differs from locked Fact Pack script")
    return {
        "result": "BLOCKED" if blockers else "CHECKPOINT_TEXT_MATCH_ONLY_HUMAN_REVIEW_REQUIRED",
        "episode_id": contract["episode_id"],
        "shotlist_sha256": contract["shotlist_sha256"],
        "expected_seconds": contract["expected_seconds"],
        "checked_checkpoint": EXPECTED_PAUSE,
        "blockers": blockers,
        "video_generated": False,
        "commercial_tts_license_verified": False,
        "semantic_scene_review_completed": False,
        "narration_timing_verified": False,
        "safe_to_resume_without_manual_approval": False,
    }


def prepare(contract: dict, destination: Path) -> dict:
    """Explicit standalone export; never writes into existing upstream task dirs."""
    destination = Path(destination).expanduser()
    if destination.exists() or destination.is_symlink():
        raise ContractError("Export target already exists: refusing overwrite")
    if destination.parent.is_symlink():
        raise ContractError("Export parent is a symlink")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "script.json").write_text(
        json.dumps(contract["scene_prompts"], ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "locked_narration.txt").write_text(contract["locked_narration"], encoding="utf-8")
    (destination / "creative_form.json").write_text(
        json.dumps(contract["form_fields"], ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "manifest.json").write_text(
        json.dumps({k: contract[k] for k in (
            "episode_id", "scene_count", "scene_durations", "expected_seconds",
            "shotlist_sha256", "factpack_sha256", "compatibility")}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {"result": "OFFLINE_EXPORT_CREATED_NOT_IMPORTED", "episode_id": contract["episode_id"],
            "scene_count": contract["scene_count"], "expected_seconds": contract["expected_seconds"],
            "files": ["script.json", "locked_narration.txt", "creative_form.json", "manifest.json"],
            "upstream_task_modified": False}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shotlist", type=Path, required=True)
    ap.add_argument("--factpack", type=Path, required=True)
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--prepare-dir", type=Path)
    modes.add_argument("--check-task", type=Path)
    args = ap.parse_args(argv)
    try:
        contract = lock_contract(args.shotlist, args.factpack)
        if args.prepare_dir:
            report = prepare(contract, args.prepare_dir)
        elif args.check_task:
            report = inspect_checkpoint(contract, args.check_task)
        else:
            report = {"result": "PLAN_ONLY_NO_CHANGES", "episode_id": contract["episode_id"],
                      "scene_count": contract["scene_count"],
                      "scene_durations": contract["scene_durations"],
                      "expected_seconds": contract["expected_seconds"],
                      "upstream_task_modified": False}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if report["result"] == "BLOCKED" else 0
    except (ContractError, OSError) as exc:
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
