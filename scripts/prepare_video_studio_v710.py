"""Prepare an isolated, pinned Agnes Video Generator checkout.

Default mode is plan-only. This tool never starts a service, installs Python
packages, reads .env, copies secrets, or applies AniFlow's v7.0.4 patch.
The pinned upstream commit is verified before any downloaded content is kept.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

VERSION = "v7.1.0"
COMMIT = "bc00ee0affa134ef67f03733d2da5ed32e3582a4"
UPSTREAM = "https://github.com/lcy362/agnes-video-generator.git"
SOURCE_FILES = (
    "start.bat",
    "server.py",
    "requirements.txt",
    "core/api/agnes_video.py",
    "core/api/retry_policy.py",
    "core/api/key_manager.py",
    "docs/public/usage.md",
)


class SafetyError(RuntimeError):
    """A verification or isolation condition has failed."""


def default_destination() -> Path:
    return Path.home() / "AniFlowExternal" / f"agnes-video-generator-{VERSION}"


def _git(*args: str) -> str:
    """Run Git without shells, user credentials, interactive prompts, or logs."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise SafetyError(f"Git unavailable or timed out ({type(exc).__name__})") from None
    if completed.returncode != 0:
        # Git diagnostics may expose proxy credentials or local paths: do not echo them.
        raise SafetyError(f"Git operation failed (exit {completed.returncode}); no output disclosed")
    return completed.stdout.strip()


def _safe_destination(destination: Path, *, must_be_new: bool) -> Path:
    destination = destination.expanduser().resolve(strict=False)
    project_root = Path(__file__).resolve().parents[1]
    if destination == project_root or project_root in destination.parents:
        raise SafetyError("Destination is inside the AniFlow Git repository; use an external directory")
    if must_be_new and (destination.exists() or destination.is_symlink()):
        raise SafetyError("Destination already exists; refuse to overwrite")
    if not must_be_new and not destination.is_dir():
        raise SafetyError("Existing checkout directory not found")
    return destination


def _source_signatures(directory: Path) -> dict[str, bool]:
    available = {name: (directory / name).is_file() for name in SOURCE_FILES}
    if not all(available.values()):
        raise SafetyError("Required upstream source files missing")
    # Only known public source files, never .env, runtime or key stores.
    try:
        video = (directory / "core/api/agnes_video.py").read_text(encoding="utf-8")
        retry = (directory / "core/api/retry_policy.py").read_text(encoding="utf-8")
        keys = (directory / "core/api/key_manager.py").read_text(encoding="utf-8")
        guide = (directory / "docs/public/usage.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise SafetyError("Unable to inspect required upstream source") from None
    checks = {
        "busy_policy": "BusyTracker" in video and "BusyTracker" in retry,
        "busy_classification": "is_busy_signal" in video and "is_busy_signal" in retry,
        "key_selection": "ring.next()" in video,
        "key_rotation": "ring.rotate()" in video,
        "auth_failure_tracking": "mark_auth_failed" in keys,
        "portrait_rotation_guide": "AGNES_FIX_V25_PORTRAIT_ROTATION" in guide,
    }
    if not all(checks.values()):
        raise SafetyError("Pinned source signatures do not match inspected v7.1.0")
    return checks


def verify_existing(destination: Path) -> dict:
    """Verify local Git provenance and static content; no execution of upstream code."""
    directory = _safe_destination(destination, must_be_new=False)
    if not (directory / ".git").exists():
        raise SafetyError("Not a Git checkout; cannot establish provenance")
    actual_root = Path(_git("-C", str(directory), "rev-parse", "--show-toplevel")).resolve()
    if actual_root != directory:
        raise SafetyError("Git repository root does not equal requested directory")
    head = _git("-C", str(directory), "rev-parse", "HEAD")
    if head != COMMIT:
        raise SafetyError("Upstream HEAD does not match the pinned official release commit")
    if _git("-C", str(directory), "status", "--porcelain", "--untracked-files=no"):
        raise SafetyError("Tracked upstream files are modified; source is not clean")
    checks = _source_signatures(directory)
    return {
        "result": "PINNED_SOURCE_VERIFIED_ONLY",
        "release": VERSION,
        "commit": head,
        "destination": str(directory),
        "source_checks": checks,
        "credentials_read": False,
        "packages_installed": False,
        "service_started": False,
        "windows_runtime_tested": False,
        "real_video_tested": False,
    }


def plan(destination: Path) -> dict:
    directory = _safe_destination(destination, must_be_new=True)
    return {
        "result": "PLAN_ONLY_NO_CHANGES",
        "release": VERSION,
        "expected_commit": COMMIT,
        "upstream": UPSTREAM,
        "destination": str(directory),
        "will_download_on_install": True,
        "will_copy_keys": False,
        "will_start_service": False,
        "will_patch_upstream": False,
        "note": "Installation requires an explicit --install; version and source checks are not live video validation.",
    }


def install(destination: Path) -> dict:
    """Explicitly fetch a pinned tag into a new location, never touching legacy."""
    directory = _safe_destination(destination, must_be_new=True)
    parent = directory.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Work in a sibling temporary directory, atomically publish only after verification.
    with tempfile.TemporaryDirectory(prefix="aniflow-v710-stage-", dir=parent) as temp:
        candidate = Path(temp) / "checkout"
        _git("clone", "--depth", "1", "--branch", VERSION, UPSTREAM, str(candidate))
        report = verify_existing(candidate)
        if directory.exists() or directory.is_symlink():
            raise SafetyError("Destination appeared during verification; refuse overwrite")
        candidate.rename(directory)
    report["destination"] = str(directory)
    report["result"] = "PINNED_SOURCE_PREPARED_NOT_STARTED"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--install", action="store_true", help="Explicitly fetch and verify isolated upstream checkout")
    choice.add_argument("--verify-existing", action="store_true", help="Read-only verification of an existing checkout")
    parser.add_argument("--dest", type=Path, default=default_destination())
    args = parser.parse_args(argv)
    try:
        if args.install:
            report = install(args.dest)
        elif args.verify_existing:
            report = verify_existing(args.dest)
        else:
            report = plan(args.dest)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except SafetyError as exc:
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
