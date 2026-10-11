"""Offline verification that no private files enter the prebuilt Windows artifact."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_nine_key_bundle import REQUIRED, build_bundle


def mock_checkout(root: Path) -> None:
    for relative in REQUIRED:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("<html>sample</html>" if target.name == "index.html" else "fake public file")
    code = root / "src" / "aniflow" / "__init__.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("# Public package")
    (root / ".env").write_text("SECRET_SHOULD_NOT_LEAK=fictional")
    (root / "src" / "aniflow" / ".private.txt").write_text("NOT_ALLOWED")


def test_allowlist_excludes_private_env_and_preserves_frontend_hash(tmp_path: Path) -> None:
    root = tmp_path / "source"
    mock_checkout(root)
    output = tmp_path / "output"
    fake_commit = "a" * 40
    manifest = build_bundle(root, output, fake_commit)
    actual = json.loads((output / "prebuilt_frontend.json").read_text(encoding="utf-8"))
    assert manifest == actual
    assert not (output / ".env").exists()
    assert not (output / "src" / "aniflow" / ".private.txt").exists()
    assert (output / "9Key使用说明.txt").is_file()
    assert actual["frontend_sha256"] == hashlib.sha256(
        (output / "apps/grok-frontend/dist/index.html").read_bytes(),
    ).hexdigest()
    assert actual["contains_credentials"] is False
    with pytest.raises(FileExistsError):
        build_bundle(root, output, fake_commit)


def test_invalid_sha_and_missing_frontend_block_package(tmp_path: Path) -> None:
    root = tmp_path / "source"
    mock_checkout(root)
    with pytest.raises(ValueError):
        build_bundle(root, tmp_path / "output", "main")
    (root / "apps/grok-frontend/dist/index.html").unlink()
    with pytest.raises(FileNotFoundError):
        build_bundle(root, tmp_path / "output", "b" * 40)
