"""Read-only compatibility audit for AniFlow's external Agnes Video Studio.

This program does not load .env, read API keys, start services, or access networks.
Source signatures are *not* equivalent to verified upstream release identity.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

EXPECTED_UPSTREAM = "v7.1.0"
LEGACY_PATCH_ANCHORS = (
    "        queue_retries = 0",
    "                        delay = _QUEUE_RETRY_BASE_DELAY + random.uniform(0, _QUEUE_RETRY_JITTER)",
)
FIRST_EPISODE = (
    "content/factpacks/MYCL-001-cat-lapping.json",
    "content/shotlists/MYCL-001-cat-lapping.json",
    "content/shotlists/MYCL-001-工单.txt",
)


def _read_text(path: Path) -> str | None:
    """Only open known source/document paths, never configuration or credentials."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError):
        return None


def inspect(repository: Path, upstream: Path | None = None) -> dict:
    """Compare known signatures without modifying repository or upstream files."""
    repository = Path(repository)
    script = _read_text(repository / "scripts" / "InstallVideoStudio.ps1")
    pinned = None
    if script is not None:
        match = re.search(r'^\s*\$Version\s*=\s*["\'](v\d+(?:\.\d+)+)["\']', script, re.M)
        pinned = match.group(1) if match else None

    episode = {name: (repository / name).is_file() for name in FIRST_EPISODE}
    result = {
        "auditor": "AniFlow video studio compatibility audit",
        "expected_upstream": EXPECTED_UPSTREAM,
        "repo": {
            "legacy_installer_present": script is not None,
            "legacy_installer_pin": pinned,
            "legacy_installer_matches_expected": pinned == EXPECTED_UPSTREAM,
            "first_episode_assets": episode,
        },
        "upstream": {
            "supplied": upstream is not None,
            "source_files_present": None,
            "new_busy_policy_signatures": None,
            "legacy_patch_anchors_present": None,
            "portrait_rotation_note_present": None,
            "release_identity_verified": False,
            "release_identity_note": "Local source patterns and folder names cannot prove a Git tag or commit.",
        },
        "safe_to_apply_legacy_patch": False,
        "safe_to_claim_windows_or_video_verified": False,
        "blockers": [],
    }

    if script is None:
        result["blockers"].append("Missing AniFlow legacy installer; repository layout not established")
    elif pinned != EXPECTED_UPSTREAM:
        result["blockers"].append(
            f"Legacy installer pin is {pinned or 'unknown'}, not {EXPECTED_UPSTREAM}; do not treat it as current"
        )

    if not all(episode.values()):
        result["blockers"].append("First episode source assets are incomplete")

    if upstream is not None:
        upstream = Path(upstream)
        video = _read_text(upstream / "core" / "api" / "agnes_video.py")
        retry = _read_text(upstream / "core" / "api" / "retry_policy.py")
        keys = _read_text(upstream / "core" / "api" / "key_manager.py")
        usage = _read_text(upstream / "docs" / "public" / "usage.md")
        present = {"video": video is not None, "retry_policy": retry is not None, "key_manager": keys is not None}
        result["upstream"]["source_files_present"] = present
        if not all(present.values()):
            result["blockers"].append("Expected upstream source files missing; incompatible or incomplete checkout")
        else:
            signatures = {
                "busy_tracker": "BusyTracker" in retry and "BusyTracker" in video,
                "busy_classifier": "is_busy_signal" in retry and "is_busy_signal" in video,
                "key_rotation": "ring.rotate()" in video,
                "key_selection": "ring.next()" in video,
                "auth_failure_diagnostics": "mark_auth_failed" in keys,
            }
            result["upstream"]["new_busy_policy_signatures"] = signatures
            if not all(signatures.values()):
                result["blockers"].append("Upstream retry and KeyRing signatures do not match inspected v7.1.0")
            result["upstream"]["legacy_patch_anchors_present"] = [anchor in video for anchor in LEGACY_PATCH_ANCHORS]
            if all(result["upstream"]["legacy_patch_anchors_present"]):
                result["blockers"].append("Legacy patch anchors present: version may be older; do not auto-patch")
        result["upstream"]["portrait_rotation_note_present"] = (
            usage is not None and "AGNES_FIX_V25_PORTRAIT_ROTATION" in usage
        )
        if usage is None:
            result["blockers"].append("Upstream usage guide missing; 9:16 known issue cannot be audited")
    else:
        result["blockers"].append("Upstream path not supplied; no source compatibility assessment")

    result["result"] = "REQUIRES_VERIFICATION" if result["blockers"] else "STATIC_SIGNATURES_MATCH_ONLY"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--upstream", type=Path, help="Read-only path to unpacked, independently verified upstream checkout")
    args = parser.parse_args(argv)
    result = inspect(args.repo, args.upstream)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "STATIC_SIGNATURES_MATCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
