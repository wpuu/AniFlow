"""Loopback-only ComfyUI transport. No AWS operations and no automatic POST retries."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

DEFAULT_DOWNLOAD_BYTES = 1024**3
FP8_DOWNLOAD_BYTES = 200 * 1024**2


class DownloadBudgetError(ValueError):
    """The existing cloud output needs recovery without another automatic media GET."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save_download_receipt(path: Path, value: dict, *, exclusive: bool = False):
    if path.is_symlink():
        raise DownloadBudgetError("Unsafe download budget path")
    target = path if exclusive else path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with target.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        if not exclusive:
            target.replace(path)
    finally:
        if not exclusive:
            target.unlink(missing_ok=True)


class ComfyProvider:
    def __init__(self, url: str, transport: httpx.BaseTransport | None = None):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError("ComfyUI must use a loopback SSM tunnel URL")
        self.client = httpx.Client(base_url=url, timeout=20, transport=transport,
                                   follow_redirects=False, trust_env=False)

    def connection_state(self) -> tuple[bool, bool]:
        """Report HTTP tunnel and observed CUDA GPU separately; CPU is not a GPU."""
        try:
            response = self.client.get("/system_stats")
            devices = response.json().get("devices")
            if response.status_code != 200 or not isinstance(devices, list):
                return False, False
            gpu = any(isinstance(device, dict) and device.get("type") == "cuda"
                      and isinstance(device.get("vram_total"), (int, float))
                      and device["vram_total"] > 0 for device in devices)
            return True, gpu
        except (httpx.HTTPError, ValueError, AttributeError):
            return False, False

    def upload(self, path: Path) -> str:
        with path.open("rb") as source:
            response = self.client.post("/upload/image", files={"image": (path.name, source)},
                                        data={"overwrite": "false", "type": "input"})
        response.raise_for_status()
        item = response.json()
        name, folder = item["name"], item.get("subfolder", "")
        if not isinstance(name, str) or "/" in name or "\\" in name or name in {"", ".", ".."}:
            raise ValueError("Invalid ComfyUI upload name")
        if not isinstance(folder, str) or ".." in folder or "\\" in folder or folder.startswith("/"):
            raise ValueError("Invalid ComfyUI upload folder")
        return f"{folder}/{name}" if folder else name

    def submit(self, workflow: dict, request_key: str) -> str:
        response = self.client.post("/prompt", json={"prompt": workflow,
            "extra_data": {"aniflow_request_key": request_key}})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]
        if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 128:
            raise ValueError("ComfyUI did not return a prompt ID")
        return prompt_id

    def inspect(self, prompt_id: str | None, request_key: str) -> tuple[str | None, str, dict | None]:
        """Recover uncertain submissions by server-stored correlation, never a guessed ID."""
        queue_response = self.client.get("/queue")
        queue_response.raise_for_status()
        queue = queue_response.json()
        for group, state in (("queue_running", "running"), ("queue_pending", "queued")):
            for item in queue.get(group, []):
                if len(item) >= 4 and (item[1] == prompt_id or
                        item[3].get("aniflow_request_key") == request_key):
                    return item[1], state, None
        response = self.client.get(f"/history/{prompt_id}" if prompt_id else "/history",
                                   params=None if prompt_id else {"max_items": 200})
        response.raise_for_status()
        for candidate, history in response.json().items():
            prompt = history.get("prompt", [])
            correlated = (len(prompt) >= 4 and isinstance(prompt[3], dict)
                          and prompt[3].get("aniflow_request_key") == request_key)
            if candidate == prompt_id or correlated:
                if history.get("status", {}).get("status_str") == "error":
                    return candidate, "failed", None
                if history.get("status", {}).get("completed"):
                    return candidate, "downloading", history
                return candidate, "running", None
        return prompt_id, "submission_unknown", None

    def download(self, history: dict, path: Path, profile: str | None = None, *,
                 max_download_bytes: int | None = None, budget_path: Path | None = None,
                 request_key: str | None = None) -> tuple[str, int, dict]:
        candidates = []
        for output in history.get("outputs", {}).values():
            for values in output.values():
                if isinstance(values, list):
                    candidates.extend(item for item in values if isinstance(item, dict)
                                      and str(item.get("filename", "")).lower().endswith(".mp4"))
        if len(candidates) != 1:
            raise ValueError("Expected exactly one MP4 from the audited workflow")
        artifact = candidates[0]
        filename, folder = artifact["filename"], artifact.get("subfolder", "")
        if (Path(filename).name != filename or "\\" in filename or ".." in folder
                or "\\" in folder or folder.startswith("/") or artifact.get("type") != "output"):
            raise ValueError("Unsafe ComfyUI output path")
        if max_download_bytes is not None:
            selected = {"filename": filename, "subfolder": folder, "type": "output"}
            return self._limited_download(selected, path, profile, max_download_bytes, budget_path, request_key)
        if budget_path is not None or request_key is not None:
            raise ValueError("An explicit byte limit is required for a download budget")
        partial = path.with_suffix(".mp4.partial")
        path.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        try:
            with self.client.stream("GET", "/view", params={"filename": filename,
                    "subfolder": folder, "type": "output"}) as response:
                response.raise_for_status()
                with partial.open("wb") as target:
                    for chunk in response.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > DEFAULT_DOWNLOAD_BYTES:
                            raise ValueError("MP4 exceeds the 1 GiB experiment limit")
                        target.write(chunk)
                        digest.update(chunk)
                length = response.headers.get("content-length")
                if length is not None and size != int(length):
                    raise ValueError("MP4 response length mismatch")
            metadata = verify_mp4(partial, profile)
            partial.replace(path)
            return digest.hexdigest(), size, metadata
        finally:
            partial.unlink(missing_ok=True)

    def _limited_download(self, artifact, path, profile, limit, budget_path, request_key):
        if (type(limit) is not int or not 0 < limit <= DEFAULT_DOWNLOAD_BYTES
                or not isinstance(budget_path, Path) or not isinstance(request_key, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_key)):
            raise DownloadBudgetError("Invalid persistent download budget")
        base = budget_path.parent.resolve()
        if budget_path.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(base):
            raise DownloadBudgetError("Download destination is outside its budget data directory")
        partial = path.with_suffix(".mp4.partial")
        if partial.is_symlink():
            raise DownloadBudgetError("Unsafe partial download path")
        binding = {"data_dir": str(base), "request_key": request_key, "destination": str(path.resolve()),
                   "artifact": artifact, "verification_profile": profile, "limit_bytes": limit}
        if budget_path.exists():
            try:
                state = json.loads(budget_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise DownloadBudgetError("Download reservation is unconfirmed; retain cloud output") from exc
            if state.get("binding") != binding or state.get("reserved_bytes") != limit:
                raise DownloadBudgetError("Download budget belongs to another request or artifact")
            verified = state.get("verified_source")
            if state.get("phase") not in {"verified", "complete"} or not isinstance(verified, dict):
                raise DownloadBudgetError("Prior media GET outcome is unknown; retain cloud output for recovery")
            source = path if path.is_file() else partial
            if (not source.is_file() or source.stat().st_size != verified.get("bytes")
                    or _file_sha256(source) != verified.get("sha256")):
                raise DownloadBudgetError("Previously verified source is missing or changed; retain cloud output")
            metadata = verify_mp4(source, profile)
            if metadata != verified.get("metadata"):
                raise DownloadBudgetError("Previously verified source metadata changed")
            if source == partial:
                partial.replace(path)
            state["phase"] = "complete"
            _save_download_receipt(budget_path, state)
            return verified["sha256"], verified["bytes"], metadata
        if path.exists() or partial.exists():
            raise DownloadBudgetError("Unknown existing media must not be overwritten")
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {"schema_version": 1, "binding": binding, "reserved_bytes": limit,
                 "attempts": 1, "phase": "reserved"}
        try:
            _save_download_receipt(budget_path, state, exclusive=True)
        except FileExistsError as exc:
            raise DownloadBudgetError("Another process owns the download reservation") from exc
        digest, size = hashlib.sha256(), 0
        try:
            with self.client.stream("GET", "/view", params=artifact) as response:
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length is not None and (not length.isdigit() or not 0 < int(length) <= limit):
                    raise DownloadBudgetError("Cloud source exceeds the reserved transfer limit")
                with partial.open("xb") as target:
                    for chunk in response.iter_bytes(min(1024 * 1024, limit)):
                        size += len(chunk)
                        if size > limit:
                            raise DownloadBudgetError("Cloud source exceeds the reserved transfer limit")
                        target.write(chunk)
                        digest.update(chunk)
                        if length is None and size == limit:
                            raise DownloadBudgetError("Unknown-length source reached its transfer limit; do not read more")
                if length is not None and size != int(length):
                    raise DownloadBudgetError("Media length is unconfirmed; do not repeat the GET")
            metadata = verify_mp4(partial, profile)
            state.update(phase="verified", verified_source={"sha256": digest.hexdigest(),
                         "bytes": size, "metadata": metadata})
            _save_download_receipt(budget_path, state)
            partial.replace(path)
            state["phase"] = "complete"
            _save_download_receipt(budget_path, state)
            return digest.hexdigest(), size, metadata
        finally:
            if state["phase"] == "reserved":
                partial.unlink(missing_ok=True)


def verify_mp4(path: Path, profile: str | None = None) -> dict:
    with path.open("rb") as source:
        if source.read(12)[4:8] != b"ftyp":
            raise ValueError("Output is not an MP4 container")
    result = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
                             "-of", "json", str(path)], capture_output=True, text=True,
                            check=True, timeout=30)
    data = json.loads(result.stdout)
    video = next(stream for stream in data["streams"] if stream.get("codec_type") == "video")
    duration = float(video.get("duration") or data["format"]["duration"])
    width, height = int(video["width"]), int(video["height"])
    numerator, denominator = video["avg_frame_rate"].split("/")
    fps = int(numerator) / int(denominator)
    frames = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
    sar = video.get("sample_aspect_ratio")
    audio = [stream for stream in data["streams"] if stream.get("codec_type") == "audio"]
    if profile == "h3_native_source":
        valid = width == 800 and height == 1376 and fps == 24 and frames >= 124
    elif profile == "wan_native_source":
        valid = width == 800 and height == 1376 and fps == 24 and frames >= 121
    elif profile in {"h3_native_final", "wan_native_final"}:
        valid = (width == 774 and height == 1376 and fps == 24 and frames == 120
                 and sar == "1:1" and abs(duration - 5) < 0.000001
                 and abs(float(data["format"]["duration"]) - 5) < 0.000001
                 and all(float(stream["duration"]) <= 5.000001 for stream in audio))
    elif profile is None:
        valid = (4.8 <= duration <= 5.2 and width >= 768 and height > width
                 and abs(width / height - 9 / 16) < 0.025 and fps > 0)
    else:
        raise ValueError("Unknown MP4 verification profile")
    if not valid:
        raise ValueError("MP4 does not satisfy the audited 5-second portrait experiment")
    # Decode every frame: ffprobe alone can accept a truncated container.
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                    "-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"], capture_output=True,
                   check=True, timeout=120)
    return {"duration_seconds": duration, "width": width, "height": height, "fps": fps,
            "frame_count": frames, "sample_aspect_ratio": sar, "audio_present": bool(audio)}


def _postprocess_portrait(source: Path, path: Path, source_profile: str,
                          final_profile: str) -> tuple[str, int, dict]:
    """Keep source frames 0..119 and crop pixels; re-encode without temporal resampling."""
    verify_mp4(source, source_profile)
    partial = path.with_suffix(".mp4.partial")
    crop = "774:1376:13:0:exact=1" if source_profile == "wan_native_source" else "774:1376:12:0"
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-y", "-i", str(source),
                        "-map", "0:v:0", "-map", "0:a:0?", "-vf",
                        f"trim=start_frame=0:end_frame=120,setpts=PTS-STARTPTS,crop={crop},setsar=1",
                        "-af", "atrim=start=0:end=5,asetpts=PTS-STARTPTS", "-fps_mode", "passthrough",
                        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-t", "5", "-movflags", "+faststart",
                        "-f", "mp4", str(partial)], capture_output=True, check=True, timeout=300)
        metadata = verify_mp4(partial, final_profile)
        digest = hashlib.sha256(partial.read_bytes()).hexdigest()
        size = partial.stat().st_size
        partial.replace(path)
        return digest, size, metadata
    finally:
        partial.unlink(missing_ok=True)


def postprocess_h3_portrait(source: Path, path: Path) -> tuple[str, int, dict]:
    return _postprocess_portrait(source, path, "h3_native_source", "h3_native_final")


def postprocess_wan_portrait(source: Path, path: Path) -> tuple[str, int, dict]:
    return _postprocess_portrait(source, path, "wan_native_source", "wan_native_final")
