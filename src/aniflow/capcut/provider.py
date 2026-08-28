from __future__ import annotations

import asyncio
import json
import shlex
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from aniflow.image_provider import ImageProvider
from aniflow.media.download import download_file
from aniflow.media.store import PublicMediaStore


@dataclass(frozen=True, slots=True)
class CapCutAutomationRequest:
    prompt: str
    model: str
    ratio: str
    reference_paths: list[str]
    output_dir: str


def _parse_command(command: str) -> list[str]:
    value = command.strip()
    if not value:
        raise ValueError("CapCut runner command must not be empty")

    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) and item for item in parsed):
            raise ValueError("CAPCUT_RUNNER_COMMAND JSON form must be a non-empty string array")
        return parsed

    # posix=True removes surrounding quotes correctly even for quoted Windows
    # paths such as "C:\\Program Files\\Python\\python.exe".
    parsed = shlex.split(value, posix=True)
    if not parsed:
        raise ValueError("CapCut runner command must not be empty")
    return parsed


def _detect_image_suffix(path: Path) -> str:
    header = path.read_bytes()[:16]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    raise RuntimeError(f"Unsupported reference image format: {path}")


class SubprocessCapCutRunner:
    """Run an external browser-automation adapter through a small JSON file protocol.

    The command receives two appended arguments:

      --request <request.json> --response <response.json>

    It must write JSON containing either `output_path` or a non-empty
    `output_paths` array. No shell is used, so prompts and paths are not
    interpreted by cmd.exe/PowerShell/bash.

    `CAPCUT_RUNNER_COMMAND` may be either a quoted command string or, for the
    most reliable Windows behavior, a JSON string array such as:

      ["python", "scripts/capcut_agent_adapter.py"]
    """

    def __init__(self, command: str, *, timeout_seconds: float = 300.0) -> None:
        self.args = _parse_command(command)
        self.timeout_seconds = timeout_seconds

    async def run(self, request: CapCutAutomationRequest) -> Path:
        with tempfile.TemporaryDirectory(prefix="aniflow-capcut-run-") as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            response_path = root / "response.json"
            request_path.write_text(
                json.dumps(asdict(request), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            args = [*self.args, "--request", str(request_path), "--response", str(response_path)]
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.communicate()
                raise RuntimeError("CapCut browser automation timed out") from None

            if process.returncode != 0:
                error_text = stderr.decode("utf-8", errors="replace").strip()
                output_text = stdout.decode("utf-8", errors="replace").strip()
                detail = error_text or output_text or f"exit code {process.returncode}"
                raise RuntimeError(f"CapCut browser automation failed: {detail[:1200]}")
            if not response_path.is_file():
                raise RuntimeError("CapCut browser automation did not write response JSON")

            data = json.loads(response_path.read_text(encoding="utf-8"))
            output_value = data.get("output_path")
            if not output_value:
                outputs = data.get("output_paths")
                if isinstance(outputs, list) and outputs:
                    output_value = outputs[0]
            if not isinstance(output_value, str) or not output_value.strip():
                raise RuntimeError("CapCut browser automation returned no output image path")

            output = Path(output_value)
            if not output.is_absolute():
                output = (root / output).resolve()
            if not output.is_file():
                raise RuntimeError(f"CapCut output image does not exist: {output}")

            # The temporary automation directory is about to be removed, so copy
            # the result into a separate named temp file for the caller.
            suffix = output.suffix.lower() if output.suffix else _detect_image_suffix(output)
            persistent_tmp = Path(tempfile.gettempdir()) / f"aniflow-capcut-{uuid4().hex}{suffix}"
            persistent_tmp.write_bytes(output.read_bytes())
            return persistent_tmp


class CapCutSeedreamProvider(ImageProvider):
    """ImageProvider backed by normal CapCut UI automation.

    This adapter intentionally does not call or reverse-engineer private CapCut
    APIs. The external runner controls the normal signed-in CapCut web/desktop UI.
    """

    def __init__(
        self,
        *,
        runner: SubprocessCapCutRunner,
        media_store: PublicMediaStore,
        model: str,
    ) -> None:
        if not model.strip():
            raise ValueError("CapCut Seedream model name must not be empty")
        self.runner = runner
        self.media_store = media_store
        self.model = model.strip()

    async def generate(
        self,
        *,
        prompt: str,
        references: list[str],
        size: str = "1K",
        ratio: str = "9:16",
    ) -> str:
        del size  # CapCut output size is selected by the browser adapter/UI.
        if not prompt.strip():
            raise ValueError("Prompt must not be empty")

        with tempfile.TemporaryDirectory(prefix="aniflow-capcut-input-") as tmp:
            root = Path(tmp)
            local_references: list[str] = []
            for index, url in enumerate(references):
                if not url.strip():
                    continue
                raw = await download_file(
                    url,
                    root / f"reference-{index}.bin",
                    timeout_seconds=180.0,
                )
                suffix = _detect_image_suffix(raw)
                path = raw.with_suffix(suffix)
                raw.replace(path)
                local_references.append(str(path))

            request = CapCutAutomationRequest(
                prompt=prompt.strip(),
                model=self.model,
                ratio=ratio,
                reference_paths=local_references,
                output_dir=str(root / "output"),
            )
            generated = await self.runner.run(request)

        try:
            suffix = generated.suffix.lower() or _detect_image_suffix(generated)
            object_key = f"aniflow/capcut/{uuid4().hex}{suffix}"
            return await self.media_store.upload(generated, object_key)
        finally:
            generated.unlink(missing_ok=True)
