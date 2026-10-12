"""Ensure Windows versions share dependencies rather than reinstall per ZIP.

Static contracts complement the real Windows Actions test that executes setup
twice and then launches the actual Bridge from the shared interpreter.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_python_runtime_installer_avoids_per_version_editable_installs() -> None:
    setup = (ROOT / "scripts/setup_aniflow_windows.ps1").read_text(encoding="utf-8")
    restart = (ROOT / "scripts/restart_aniflow_windows.ps1").read_text(encoding="utf-8")
    runtime = (ROOT / "scripts/aniflow_shared_runtime.ps1").read_text(encoding="utf-8")

    for script in (setup, restart):
        assert "Get-AniFlowRuntimePython" in script
        assert 'pip install -e .' not in script
        assert '.venv\\Scripts\\python.exe' not in script
        assert 'Join-Path $RepoRoot "src"' in script or 'Join-Path $Root "src"' in script

    assert "LocalApplicationData" in runtime
    assert "aniflow_runtime_probe.py" in runtime
    assert " $ProbeFile requirements $RepoRoot" in runtime
    probe = (ROOT / "scripts/aniflow_runtime_probe.py").read_text(encoding="utf-8")
    assert 'spec["project"]["dependencies"]' in probe
    assert "ANIFLOW_CURRENT_SOURCE_OK" in probe
    assert "AniFlow\\python-env" in runtime
    assert "dependencies-sha256.txt" in runtime
    assert 'spec["project"]["dependencies"]' in probe
    assert "PASS_ANIFLOW_SHARED_RUNTIME_REUSED_NO_PIP" in runtime
    assert "if ($CurrentFingerprint -eq $Fingerprint -and $Healthy)" in runtime
    assert "pip install --disable-pip-version-check @Requirements" in runtime
    assert "AGNES_API_KEY" not in runtime


def test_bundle_includes_shared_runtime_helper() -> None:
    from scripts.build_nine_key_bundle import REQUIRED

    assert "scripts/aniflow_shared_runtime.ps1" in REQUIRED
    assert "scripts/aniflow_runtime_probe.py" in REQUIRED
    assert "scripts/setup_aniflow_windows.ps1" in REQUIRED
    assert "scripts/restart_aniflow_windows.ps1" in REQUIRED
