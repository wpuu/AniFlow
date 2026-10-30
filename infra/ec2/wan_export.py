"""Read-only, single-job Wan observer. Never submits or retries Comfy generation."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import signal
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit
from urllib.request import urlopen

from botocore.exceptions import BotoCoreError, ClientError


class ExportError(RuntimeError):
    pass


class Deadline(ExportError):
    pass


def utc_now():
    return datetime.now(UTC)


def parse_utc(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ExportError("deadline_utc must have an explicit UTC offset")
    return result


def validate_config(config):
    if config["region"] != "us-east-2":
        raise ExportError("Only us-east-2 is allowed")
    if not re.fullmatch(r"aniflow-wan-ohio-20261027-[a-z0-9-]+", config["experiment_id"]):
        raise ExportError("Invalid experiment_id")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", config["bucket"]):
        raise ExportError("Invalid bucket name")
    url = urlsplit(config["comfy_url"])
    try:
        loopback = ipaddress.ip_address(url.hostname or "").is_loopback
    except ValueError:
        loopback = url.hostname == "localhost"
    if (url.scheme != "http" or not loopback or url.username or url.password
            or url.query or url.fragment or url.path not in ("", "/")):
        raise ExportError("Comfy URL must be a loopback HTTP origin")
    if not Path(config["output_root"]).is_absolute():
        raise ExportError("output_root must be absolute")
    parse_utc(config["deadline_utc"])
    for key in ("ffmpeg_path", "ffprobe_path"):
        if not Path(config[key]).is_absolute() or not Path(config[key]).is_file():
            raise ExportError("Media executable must be an existing absolute path")
    return config


def remaining(config, now=utc_now):
    seconds = (parse_utc(config["deadline_utc"]) - now()).total_seconds()
    if seconds <= 0:
        raise Deadline("Export deadline reached")
    return seconds


def get_json(config, endpoint):
    if endpoint not in ("/queue", "/history"):
        raise ExportError("Read-only endpoint violation")
    with urlopen(config["comfy_url"].rstrip("/") + endpoint,
                 timeout=min(15, remaining(config))) as response:
        return json.load(response)


def task_identity(item):
    if not isinstance(item, (list, tuple)) or len(item) < 4:
        return None
    prompt_id, workflow, extra = item[1:4]
    if not isinstance(workflow, dict) or not isinstance(extra, dict):
        return None
    key = extra.get("aniflow_request_key", "")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
        return None
    if not any(isinstance(node, dict) and node.get("class_type") == "WanImageToVideo"
               for node in workflow.values()):
        return None
    if not isinstance(prompt_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", prompt_id):
        raise ExportError("Invalid prompt_id")
    return {"prompt_id": prompt_id, "request_key": key}


def select_task(queue, history):
    items = list(queue.get("queue_running", [])) + list(queue.get("queue_pending", []))
    items += [value.get("prompt") for value in history.values() if isinstance(value, dict)]
    candidates = {}
    for item in items:
        identity = task_identity(item)
        if identity:
            pair = identity["prompt_id"], identity["request_key"]
            candidates[pair] = identity
    if len(candidates) > 1:
        raise ExportError("Ambiguous Wan tasks; refusing automatic selection")
    return next(iter(candidates.values()), None)


def source_path(job, output_root):
    candidates = []

    def visit(value):
        if isinstance(value, dict):
            if (value.get("type") == "output" and isinstance(value.get("filename"), str)
                    and value["filename"].lower().endswith(".mp4")):
                candidates.append(value)
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(job.get("outputs", {}))
    if len(candidates) != 1:
        raise ExportError("Expected exactly one output MP4")
    item = candidates[0]
    folder, filename = item.get("subfolder", ""), item["filename"]
    if not isinstance(folder, str):
        raise ExportError("Invalid output subfolder")
    for component in (folder, filename):
        posix, windows = PurePosixPath(component), PureWindowsPath(component)
        if (posix.is_absolute() or windows.drive or windows.root
                or ".." in posix.parts or ".." in windows.parts or "\\" in component):
            raise ExportError("Output path escape")
    if len(PurePosixPath(filename).parts) != 1:
        raise ExportError("Filename must not contain directories")
    root = Path(output_root).resolve(strict=True)
    result = (root / folder / filename).resolve(strict=True)
    if not result.is_relative_to(root) or not result.is_file():
        raise ExportError("Output path escapes output_root")
    return result


def run_media(config, args):
    return subprocess.run(args, capture_output=True, check=True, text=True,
                          timeout=min(300, remaining(config)))


def verify_media(config, path, final=False):
    with path.open("rb") as source:
        if source.read(12)[4:8] != b"ftyp":
            raise ExportError("Not an MP4 container")
    data = json.loads(run_media(config, [config["ffprobe_path"], "-v", "error", "-count_frames",
                                        "-show_streams", "-show_format", "-of", "json",
                                        str(path)]).stdout)
    streams = [stream for stream in data["streams"] if stream.get("codec_type") == "video"]
    if len(streams) != 1:
        raise ExportError("Expected one video stream")
    video = streams[0]
    fps = float(Fraction(video["avg_frame_rate"]))
    frames = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
    duration = float(video.get("duration") or data["format"]["duration"])
    valid = (int(video["width"]) == (774 if final else 800)
             and int(video["height"]) == 1376 and fps == 24
             and (frames == 120 if final else frames >= 121))
    if final:
        valid = (valid and video.get("sample_aspect_ratio") == "1:1"
                 and abs(duration - 5) < 0.000001
                 and abs(float(data["format"]["duration"]) - 5) < 0.000001
                 and all(float(s["duration"]) <= 5.000001 for s in data["streams"]
                         if s.get("codec_type") == "audio"))
    if not valid:
        raise ExportError("Video does not meet the Wan portrait specification")
    run_media(config, [config["ffmpeg_path"], "-v", "error", "-xerror", "-i", str(path),
                       "-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"])
    return {"width": int(video["width"]), "height": int(video["height"]), "fps": fps,
            "frame_count": frames, "duration_seconds": duration,
            "sample_aspect_ratio": video.get("sample_aspect_ratio")}


def postprocess(config, source, final):
    partial = final.with_suffix(".partial.mp4")
    try:
        run_media(config, [config["ffmpeg_path"], "-v", "error", "-xerror", "-y", "-i",
                           str(source), "-map", "0:v:0", "-map", "0:a:0?", "-vf",
                           ("trim=end_frame=120,setpts=PTS-STARTPTS,"
                            "crop=774:1376:13:0:exact=1,setsar=1"),
                           "-af", "atrim=end=5,asetpts=PTS-STARTPTS", "-fps_mode", "passthrough",
                           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt",
                           "yuv420p", "-c:a", "aac", "-t", "5", "-movflags", "+faststart",
                           "-f", "mp4", str(partial)])
        metadata = verify_media(config, partial, final=True)
        partial.replace(final)
        return metadata
    finally:
        partial.unlink(missing_ok=True)


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def save_receipt(path, receipt):
    partial = path.with_suffix(".tmp")
    if path.is_symlink() or partial.is_symlink():
        raise ExportError("Receipt symlink is not allowed")
    with partial.open("w", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    partial.replace(path)


@contextmanager
def process_lock(path):
    with path.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if not handle.read(1):
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ExportError("Another exporter owns this experiment") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def upload(config, client, path, key, receipt, receipt_path, sleep=time.sleep):
    record = receipt.setdefault("uploads", {}).setdefault(key, {"attempts": 0})
    info = fingerprint(path)
    if record.get("complete"):
        if record.get("sha256") != info["sha256"]:
            raise ExportError("Previously uploaded content changed")
        return
    if record.get("sha256", info["sha256"]) != info["sha256"]:
        raise ExportError("Retry object content changed")
    record.update(info)
    while record["attempts"] < 3:
        remaining(config)
        record["attempts"] += 1
        save_receipt(receipt_path, receipt)
        try:
            with path.open("rb") as body:
                client.put_object(Bucket=config["bucket"], Key=key, Body=body,
                                  ServerSideEncryption="AES256",
                                  ContentType="application/json" if key.endswith(".json")
                                  else "video/mp4", Metadata={"sha256": info["sha256"]})
            record["complete"] = True
            save_receipt(receipt_path, receipt)
            return
        except (BotoCoreError, ClientError, OSError):
            if record["attempts"] < 3:
                sleep(min(2, remaining(config)))
    raise ExportError("S3 upload attempts exhausted")


def export_once(config, client, state, receipt, receipt_path):
    prefix = "experiments/" + config["experiment_id"]
    prompt_id = receipt["selection"]["prompt_id"]
    source = Path(receipt["source_path"])
    root = Path(config["output_root"]).resolve(strict=True)
    if not source.resolve(strict=True).is_relative_to(root):
        raise ExportError("Saved source path escaped output_root")
    final = state / (prompt_id + ".mp4")
    manifest_path = state / (prompt_id + ".json")
    if final.is_symlink() or manifest_path.is_symlink():
        raise ExportError("Export artifact symlink is not allowed")
    if "media" not in receipt:
        source_metadata = verify_media(config, source)
        final_metadata = postprocess(config, source, final)
        receipt["media"] = {"source": {**fingerprint(source), "metadata": source_metadata},
                            "final": {**fingerprint(final), "metadata": final_metadata}}
        receipt["observed_elapsed_seconds"] = max(
            0, (utc_now() - parse_utc(receipt["observed_at_utc"])).total_seconds())
        save_receipt(receipt_path, receipt)
    for kind, path in (("source", source), ("final", final)):
        if fingerprint(path) != {key: receipt["media"][kind][key] for key in ("sha256", "bytes")}:
            raise ExportError("Verified media changed")
        suffix = ".source.mp4" if kind == "source" else ".mp4"
        upload(config, client, path, prefix + "/outputs/" + prompt_id + suffix,
               receipt, receipt_path)
    save_receipt(manifest_path, {"experiment_id": config["experiment_id"],
                                "model": "wan2.2-i2v-a14b",
                                **receipt["selection"], "media": receipt["media"],
                                "observed_elapsed_seconds": receipt["observed_elapsed_seconds"],
                                "gpu_vram_peak_bytes": None,
                                "inference_elapsed_seconds": None,
                                "cost_usd": None})
    upload(config, client, manifest_path, prefix + "/reports/" + prompt_id + ".json",
           receipt, receipt_path)
    receipt["complete"] = True
    save_receipt(receipt_path, receipt)


def observe(config, client, get=get_json, sleep=time.sleep):
    validate_config(config)
    state = Path(config["output_root"]) / ".aniflow-export" / config["experiment_id"]
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not state.resolve().is_relative_to(Path(config["output_root"]).resolve()):
        raise ExportError("State directory escape")
    receipt_path = state / "receipt.json"
    if receipt_path.is_symlink() or (state / "export.lock").is_symlink():
        raise ExportError("State file symlink is not allowed")
    with process_lock(state / "export.lock"):
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        binding = {key: config[key] for key in ("region", "bucket", "experiment_id", "comfy_url",
                                                "output_root", "deadline_utc")}
        if receipt.get("binding", binding) != binding:
            raise ExportError("Persisted export configuration changed")
        receipt["binding"] = binding
        save_receipt(receipt_path, receipt)
        if receipt.get("complete"):
            return receipt
        failures = 0
        while True:
            remaining(config)
            if "source_path" in receipt:
                export_once(config, client, state, receipt, receipt_path)
                return receipt
            try:
                queue, history = get(config, "/queue"), get(config, "/history")
            except (OSError, ValueError):
                failures += 1
                if failures >= 3:
                    raise ExportError("Comfy observation attempts exhausted") from None
                sleep(min(5, remaining(config)))
                continue
            failures = 0
            if "selection" not in receipt:
                selected = select_task(queue, history)
                if selected:
                    receipt.update(selection=selected, observed_at_utc=utc_now().isoformat())
                    save_receipt(receipt_path, receipt)
            if "selection" in receipt:
                selected = receipt["selection"]
                job = history.get(selected["prompt_id"])
                if job:
                    if task_identity(job.get("prompt")) != selected:
                        raise ExportError("History correlation changed")
                    status = job.get("status", {})
                    if status.get("status_str") == "error":
                        raise ExportError("Selected Wan task failed; no resubmission")
                    if status.get("completed") and status.get("status_str") == "success":
                        receipt["source_path"] = str(source_path(job, config["output_root"]))
                        save_receipt(receipt_path, receipt)
                        continue
            sleep(min(5, remaining(config)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        config = validate_config(json.loads(args.config.read_text(encoding="utf-8")))
        remaining(config)
        if os.name != "nt":
            def deadline_alarm(_number, _frame):
                raise Deadline("Export deadline reached")

            signal.signal(signal.SIGALRM, deadline_alarm)
            signal.setitimer(signal.ITIMER_REAL, remaining(config))
        import boto3
        from botocore.config import Config
        client = boto3.client("s3", region_name="us-east-2", config=Config(
            retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=15))
        observe(config, client)
        print("WAN_EXPORT_COMPLETE")
    except Exception as exc:  # noqa: BLE001 -- CLI boundary must redact all exception details.
        # Do not print server messages, credentials, URLs, prompts, or request bodies.
        print("WAN_EXPORT_STOPPED:" + type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        if os.name != "nt":
            signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
