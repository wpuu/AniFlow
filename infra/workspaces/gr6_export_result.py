"""Export one already-submitted Comfy job; never submit or discover other jobs."""

import hashlib
import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ExportError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExportError("HTTP_REDIRECT_REFUSED")


class DeadlineReader:
    def __init__(self, source, deadline):
        self.source, self.deadline = source, deadline

    def read(self, size=-1):
        remaining(self.deadline)
        return self.source.read(size)


def open_request(request, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


def remaining(deadline):
    seconds = deadline - time.time()
    if seconds <= 0:
        raise ExportError("DEADLINE_REACHED")
    return min(seconds, 30)


def load_config(path):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    prompt_id = config["prompt_id"]
    if not isinstance(prompt_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", prompt_id):
        raise ExportError("INVALID_PROMPT_ID")
    base = urlsplit(config["comfy_url"])
    try:
        loopback = base.hostname == "localhost" or ipaddress.ip_address(base.hostname).is_loopback
    except ValueError:
        loopback = False
    if (not loopback or base.scheme not in ("http", "https") or base.username or base.password
            or base.query or base.fragment or base.path not in ("", "/")):
        raise ExportError("COMFY_MUST_BE_LOOPBACK")
    config["comfy_url"] = config["comfy_url"].rstrip("/")
    root = Path(config["output_root"]).resolve(strict=True)
    if not root.is_dir():
        raise ExportError("INVALID_OUTPUT_ROOT")
    config["output_root"] = root
    for key in ("expected_width", "expected_height"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ExportError("INVALID_EXPECTED_DIMENSIONS")
    end = datetime.fromisoformat(config["deadline_utc"])
    if end.tzinfo is None:
        raise ExportError("DEADLINE_NEEDS_TIMEZONE")
    config["deadline"] = end.timestamp()
    hosts = []
    for key, prefix in (("video_put_url", "/outputs/"), ("manifest_put_url", "/reports/")):
        url = urlsplit(config[key])
        host = url.hostname or ""
        query = parse_qs(url.query)
        if (url.scheme != "https" or url.username or url.password or url.fragment
                or url.port not in (None, 443)
                or not any(host.endswith(suffix) for suffix in (
                    ".s3.ap-northeast-1.amazonaws.com",
                    ".s3.dualstack.ap-northeast-1.amazonaws.com"))
                or not url.path.startswith(prefix)
                or not {"X-Amz-Signature", "X-Amz-Credential"}.issubset(query)):
            raise ExportError("INVALID_PRIVATE_PUT_URL")
        hosts.append(host)
    if hosts[0] != hosts[1]:
        raise ExportError("PUT_DESTINATIONS_MUST_SHARE_BUCKET")
    return config


def completed_video(history, prompt_id, root):
    job = history.get(prompt_id)
    if job is None:
        return None
    status = job.get("status", {})
    if status.get("status_str") == "error" or any(
        item and item[0] == "execution_error" for item in status.get("messages", [])
    ):
        raise ExportError("COMFY_JOB_FAILED")
    if not status.get("completed"):
        return None
    if status.get("status_str") != "success":
        raise ExportError("COMFY_SUCCESS_NOT_CONFIRMED")
    candidates = set()

    def visit(value):
        if isinstance(value, dict):
            name = value.get("filename")
            if isinstance(name, str) and name.lower().endswith(".mp4"):
                if value.get("type") != "output":
                    raise ExportError("MP4_MUST_BE_FINAL_OUTPUT")
                candidates.add((name, value.get("subfolder", "")))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(job.get("outputs", {}))
    if len(candidates) != 1:
        raise ExportError("EXPECTED_EXACTLY_ONE_MP4")
    name, folder = candidates.pop()
    if ("/" in name or "\\" in name or PureWindowsPath(name).drive
            or not isinstance(folder, str) or PureWindowsPath(folder).drive
            or Path(folder).is_absolute()):
        raise ExportError("OUTPUT_PATH_ESCAPE")
    path = (root / folder / name).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ExportError("OUTPUT_PATH_ESCAPE")
    if not path.is_file() or path.stat().st_size == 0:
        raise ExportError("MP4_MISSING_OR_EMPTY")
    return path


def probe_video(path, config):
    try:
        response = subprocess.run([
            config["ffprobe_path"], "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_type,width,height,duration:format=duration",
            "-of", "json", str(path),
        ], capture_output=True, text=True, timeout=remaining(config["deadline"]), check=True)
        probe = json.loads(response.stdout)
        stream = probe["streams"][0]
        duration = stream.get("duration")
        if duration in (None, "N/A"):
            duration = probe["format"]["duration"]
        duration = float(duration)
        if (stream.get("codec_type") != "video" or not math.isfinite(duration)
                or abs(duration - 5) > 0.05
                or stream["width"] != config["expected_width"]
                or stream["height"] != config["expected_height"]):
            raise ExportError("VIDEO_SPEC_MISMATCH")
        return {"duration_seconds": duration, "width": stream["width"], "height": stream["height"]}
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError):
        raise ExportError("FFPROBE_FAILED") from None


def digest(path, deadline):
    sha = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            remaining(deadline)
            sha.update(chunk)
    return sha.hexdigest()


def put(url, data, length, content_type, deadline):
    for attempt in range(3):
        try:
            if hasattr(data, "seek"):
                data.seek(0)
            body = DeadlineReader(data, deadline) if hasattr(data, "read") else data
            request = Request(url, data=body, method="PUT", headers={
                "Content-Length": str(length), "Content-Type": content_type})
            with open_request(request, remaining(deadline)) as response:
                if not 200 <= response.status < 300:
                    raise ExportError("UPLOAD_REJECTED")
            return
        except (HTTPError, URLError, TimeoutError, OSError):
            if attempt == 2:
                raise ExportError("UPLOAD_FAILED") from None
            time.sleep(min(1, remaining(deadline)))


def save_receipt(path, receipt):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    temporary.replace(path)


def export(config_path):
    config_path = Path(config_path).resolve(strict=True)
    config = load_config(config_path)
    prompt_id = config["prompt_id"]
    receipt_path = config_path.parent / f"h3-export-{prompt_id}.receipt.json"
    lock_path = receipt_path.with_suffix(".lock")
    try:
        lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ExportError("EXPORT_LOCKED_RECONCILIATION_REQUIRED") from None
    os.close(lock)
    try:
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if receipt:
            if (receipt.get("prompt_id") != prompt_id
                    or receipt.get("state") not in ("SAVED", "VIDEO_SAVED_MANIFEST_PENDING")
                    or receipt["ffprobe"]["width"] != config["expected_width"]
                    or receipt["ffprobe"]["height"] != config["expected_height"]):
                raise ExportError("EXISTING_RECEIPT_MISMATCH")
            if receipt["state"] == "SAVED":
                return receipt
        else:
            while True:
                request = Request(f"{config['comfy_url']}/history/{prompt_id}", method="GET")
                try:
                    with open_request(request, remaining(config["deadline"])) as response:
                        history = json.load(response)
                except (HTTPError, URLError, TimeoutError, OSError):
                    time.sleep(min(2, remaining(config["deadline"])))
                    continue
                if not isinstance(history, dict):
                    raise ExportError("INVALID_COMFY_HISTORY")
                video = completed_video(history, prompt_id, config["output_root"])
                if video:
                    break
                time.sleep(min(2, remaining(config["deadline"])))
            probe = probe_video(video, config)
            size = video.stat().st_size
            sha = digest(video, config["deadline"])
            with video.open("rb") as source:
                put(config["video_put_url"], source, size, "video/mp4", config["deadline"])
            receipt = {"prompt_id": prompt_id, "state": "VIDEO_SAVED_MANIFEST_PENDING",
                       "filename": video.name, "bytes": size, "sha256": sha, "ffprobe": probe}
            save_receipt(receipt_path, receipt)
        manifest = {k: v for k, v in receipt.items() if k != "state"}
        payload = json.dumps(manifest, sort_keys=True).encode("utf-8")
        put(config["manifest_put_url"], payload, len(payload), "application/json", config["deadline"])
        receipt.update(state="SAVED", saved_at_utc=datetime.now(UTC).isoformat())
        save_receipt(receipt_path, receipt)
        return receipt
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        result = export(sys.argv[1])
    except Exception as error:  # noqa: BLE001 - Never expose signed URLs through a CLI traceback.
        result = {"state": "FAILED", "error_type": type(error).__name__,
                  "code": str(error) if isinstance(error, ExportError) else "EXPORT_FAILED"}
    print(json.dumps(result))
    raise SystemExit(0 if result["state"] == "SAVED" else 2)
