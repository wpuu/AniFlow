"""Stdlib-only checks used by AniFlow's shared Windows Python runtime.

Called as a script by PowerShell to avoid WinPS 5.1 losing quoting in
multiline python -c arguments. Does not read API keys or contact Agnes.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import pathlib
import sys
import tomllib


REQUIRED_DISTRIBUTIONS = (
    "boto3",
    "fastapi",
    "httpx",
    "pydantic",
    "pydantic-settings",
    "python-dotenv",
    "python-multipart",
    "typer",
    "uvicorn",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("requirements", "health", "source"))
    parser.add_argument("root", nargs="?")
    args = parser.parse_args()

    if sys.version_info < (3, 11):
        print("ANIFLOW_RUNTIME_PYTHON_TOO_OLD")
        return 2

    if args.mode == "requirements":
        if not args.root:
            return 2
        project = pathlib.Path(args.root) / "pyproject.toml"
        spec = tomllib.loads(project.read_text(encoding="utf-8"))
        requirements = sorted(spec["project"]["dependencies"])
        if not requirements:
            return 2
        result = {
            "requirements": requirements,
            "python": list(sys.version_info[:2]),
        }
        print(json.dumps(result, separators=(",", ":")))
        return 0

    if args.mode == "health":
        missing = []
        for name in REQUIRED_DISTRIBUTIONS:
            try:
                metadata.version(name)
            except metadata.PackageNotFoundError:
                missing.append(name)
        print("ANIFLOW_SHARED_RUNTIME_MISSING" if missing else "ANIFLOW_SHARED_RUNTIME_HEALTH_OK")
        return 0

    if not args.root:
        return 2
    import aniflow  # Loaded from PYTHONPATH set by current release launcher.

    expected = (pathlib.Path(args.root) / "src" / "aniflow" / "__init__.py").resolve()
    if pathlib.Path(aniflow.__file__).resolve() != expected:
        print("ANIFLOW_SOURCE_VERSION_MISMATCH")
        return 7
    print("ANIFLOW_CURRENT_SOURCE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
