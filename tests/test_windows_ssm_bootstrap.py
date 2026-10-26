import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "infra/workspaces/windows-ssm-bootstrap.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


def run_guard(tmp_path, function_name, mocks):
    if not POWERSHELL:
        pytest.skip("PowerShell is required for the Windows bootstrap guards")
    script_path = str(SCRIPT).replace("'", "''")
    harness = tmp_path / "guard.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$tokens = $null; $errors = $null\n"
        f"$ast = [System.Management.Automation.Language.Parser]::ParseFile('{script_path}', "
        "[ref]$tokens, [ref]$errors)\n"
        "if ($errors.Count) { throw 'Script parse failure' }\n"
        "$ast.FindAll({param($node) $node -is "
        "[System.Management.Automation.Language.FunctionDefinitionAst]}, $true) | "
        "ForEach-Object { Invoke-Expression $_.Extent.Text }\n"
        + mocks
        + f"\ntry {{ {function_name}; Write-Output 'ALLOWED' }} "
        "catch { Write-Output 'BLOCKED' }\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(harness)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    return result.stdout.strip()


@pytest.mark.parametrize("status", ["Running", "Stopped"])
def test_existing_agent_is_never_overwritten(tmp_path, status):
    mocks = f"function Get-Service {{ [pscustomobject]@{{ Status = '{status}' }} }}"
    assert run_guard(tmp_path, "Assert-NewHybridNode", mocks) == "BLOCKED"


def test_orphan_registration_is_not_overwritten(tmp_path):
    mocks = "function Get-Service { $null }; function Test-Path { $true }"
    assert run_guard(tmp_path, "Assert-NewHybridNode", mocks) == "BLOCKED"


@pytest.mark.parametrize("status,subject,expected", [
    ("Valid", "CN=Amazon.com Services LLC, O=Amazon.com Services LLC, C=US", "ALLOWED"),
    ("HashMismatch", "CN=Amazon.com Services LLC, C=US", "BLOCKED"),
    ("NotSigned", "", "BLOCKED"),
    ("Valid", "CN=Unrelated Publisher, C=US", "BLOCKED"),
    ("Valid", "CN=Fake Amazon.com Services LLC Evil, C=US", "BLOCKED"),
])
def test_signature_validation_fails_closed(tmp_path, status, subject, expected):
    values = json.dumps({"Status": status, "SignerCertificate": {"Subject": subject}})
    mocks = f"function Get-AuthenticodeSignature {{ '{values}' | ConvertFrom-Json }}"
    assert run_guard(tmp_path, "Assert-TrustedSetup 'unused.exe'", mocks) == expected
