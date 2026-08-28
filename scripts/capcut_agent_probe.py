from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CAPCUT_AI_DESIGN_URL = "https://www.capcut.com/tools/ai-design"
DEFAULT_SESSION = "aniflow-capcut"
DEFAULT_RUNTIME = Path("data/runtime/capcut")


def _agent_browser() -> str:
    binary = shutil.which("agent-browser")
    if not binary:
        raise SystemExit(
            "agent-browser was not found on PATH. Install/configure the browser Agent first; "
            "AniFlow will not guess CapCut selectors without a real logged-in probe."
        )
    return binary


def _run(session: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [_agent_browser(), "--session", session, *args]
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def open_browser(session: str) -> None:
    subprocess.run(
        [_agent_browser(), "--session", session, "--headed", "open", CAPCUT_AI_DESIGN_URL],
        check=True,
    )
    print(
        "CapCut AI Design has been opened in a persistent headed browser session.\n"
        "Log in normally if required, navigate to the actual image-generation workspace, "
        "select the Seedream model you want to use, then run:\n\n"
        f"  python scripts/capcut_agent_probe.py capture --session {session}\n"
    )


def capture(session: str, runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _run(session, "snapshot", "-i", "-C").stdout
    body_text = _run(session, "get", "text", "body").stdout
    current_url = _run(session, "get", "url").stdout.strip()
    title = _run(session, "get", "title").stdout.strip()

    state_path = runtime_dir / "browser-state.json"
    _run(session, "state", "save", str(state_path))

    (runtime_dir / "snapshot.txt").write_text(snapshot, encoding="utf-8")
    (runtime_dir / "body.txt").write_text(body_text, encoding="utf-8")
    metadata = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "session": session,
        "url": current_url,
        "title": title,
        "state_path": str(state_path),
        "note": (
            "browser-state.json may contain authenticated session data. "
            "data/runtime is gitignored and must remain private."
        ),
    }
    (runtime_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Captured CapCut UI probe to: {runtime_dir.resolve()}")
    print(f"URL: {current_url}")
    print(f"Title: {title}")
    print("Files: snapshot.txt, body.txt, metadata.json, browser-state.json")


def resume(session: str, runtime_dir: Path) -> None:
    state_path = runtime_dir / "browser-state.json"
    if not state_path.is_file():
        raise SystemExit(f"No saved CapCut browser state found at {state_path}")
    _run(session, "state", "load", str(state_path))
    subprocess.run(
        [_agent_browser(), "--session", session, "--headed", "open", CAPCUT_AI_DESIGN_URL],
        check=True,
    )
    print("Saved CapCut session state loaded and AI Design opened.")


def close(session: str) -> None:
    _run(session, "close", check=False)
    print(f"Closed browser session: {session}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover the real logged-in CapCut AI Design UI before writing a stable AniFlow adapter."
    )
    parser.add_argument("action", choices=["open", "capture", "resume", "close"])
    parser.add_argument("--session", default=DEFAULT_SESSION)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()

    if args.action == "open":
        open_browser(args.session)
    elif args.action == "capture":
        capture(args.session, args.runtime_dir)
    elif args.action == "resume":
        resume(args.session, args.runtime_dir)
    else:
        close(args.session)


if __name__ == "__main__":
    main()
