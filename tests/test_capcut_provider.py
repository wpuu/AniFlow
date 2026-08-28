from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from aniflow.capcut.provider import (
    CapCutAutomationRequest,
    CapCutSeedreamProvider,
    SubprocessCapCutRunner,
    _parse_command,
)


class FakeRunner:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.requests: list[CapCutAutomationRequest] = []

    async def run(self, request: CapCutAutomationRequest) -> Path:
        self.requests.append(request)
        output = self.tmp_path / "seedream.png"
        output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"generated")
        return output


class FakeStore:
    def __init__(self) -> None:
        self.uploads: list[tuple[bytes, str]] = []

    async def upload(self, local_path: Path, object_key: str) -> str:
        self.uploads.append((local_path.read_bytes(), object_key))
        return f"https://media.example/{object_key}"


def test_parse_command_accepts_json_array_for_windows_safe_configuration() -> None:
    assert _parse_command('["python", "scripts/capcut_agent_adapter.py"]') == [
        "python",
        "scripts/capcut_agent_adapter.py",
    ]


def test_parse_command_removes_quotes_from_paths_with_spaces() -> None:
    parsed = _parse_command('"C:\\Program Files\\Python\\python.exe" "C:\\Ani Flow\\adapter.py"')
    assert parsed == [
        "C:\\Program Files\\Python\\python.exe",
        "C:\\Ani Flow\\adapter.py",
    ]


@pytest.mark.asyncio
async def test_capcut_provider_uploads_generated_output(tmp_path: Path) -> None:
    runner = FakeRunner(tmp_path)
    store = FakeStore()
    provider = CapCutSeedreamProvider(
        runner=runner,  # type: ignore[arg-type]
        media_store=store,  # type: ignore[arg-type]
        model="Seedream 5.0",
    )

    url = await provider.generate(
        prompt="same fox, new pose",
        references=[],
        ratio="9:16",
    )

    assert url.startswith("https://media.example/aniflow/capcut/")
    assert runner.requests[0].model == "Seedream 5.0"
    assert runner.requests[0].ratio == "9:16"
    assert store.uploads[0][1].startswith("aniflow/capcut/")
    assert store.uploads[0][1].endswith(".png")


@pytest.mark.asyncio
async def test_subprocess_runner_json_protocol(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--request', required=True)
parser.add_argument('--response', required=True)
args = parser.parse_args()
request = json.loads(Path(args.request).read_text(encoding='utf-8'))
output_dir = Path(request['output_dir'])
output_dir.mkdir(parents=True, exist_ok=True)
output = output_dir / 'result.png'
output.write_bytes(b'\\x89PNG\\r\\n\\x1a\\nresult')
Path(args.response).write_text(json.dumps({'output_path': str(output)}), encoding='utf-8')
""".strip(),
        encoding="utf-8",
    )

    runner = SubprocessCapCutRunner(
        json.dumps([sys.executable, str(adapter)]),
        timeout_seconds=30,
    )
    request = CapCutAutomationRequest(
        prompt="test",
        model="Seedream 5.0",
        ratio="9:16",
        reference_paths=[],
        output_dir=str(tmp_path / "ignored-by-runner"),
    )

    output = await runner.run(request)
    try:
        assert output.is_file()
        assert output.suffix == ".png"
        assert output.read_bytes().startswith(b"\x89PNG")
    finally:
        output.unlink(missing_ok=True)
