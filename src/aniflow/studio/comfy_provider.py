"""Loopback-only ComfyUI transport. No AWS operations and no automatic POST retries."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import httpx


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

    def download(self, history: dict, path: Path,
                 profile: str | None = None) -> tuple[str, int, dict]:
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
                        if size > 1024 * 1024 * 1024:
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
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-y", "-i", str(source),
                        "-map", "0:v:0", "-map", "0:a:0?", "-vf",
                        "trim=start_frame=0:end_frame=120,setpts=PTS-STARTPTS,crop=774:1376:12:0,setsar=1",
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
