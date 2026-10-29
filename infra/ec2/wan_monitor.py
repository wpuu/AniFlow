"""Read-only single-request Wan execution telemetry; never submits or verifies media.

Stage this file on the GPU host and run its CLI before the unique generation POST.
Use --request-key KEY --deadline-utc UTC --output /absolute/private/report.json.
The existing wan_export.py runs independently with --config /absolute/config.json.
Its JSON fields are region, bucket, experiment_id, comfy_url, output_root,
deadline_utc, ffmpeg_path and ffprobe_path. Media/S3 receipts remain separate.
"""

import argparse
import csv
import ipaddress
import json
import math
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class MonitorError(RuntimeError):
    pass


def utc_now():
    return datetime.now(UTC)


def parse_deadline(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise MonitorError("Deadline must have an explicit UTC offset")
    return result


def validate_config(config, now):
    origin = urlsplit(config["comfy_url"])
    try:
        local = ipaddress.ip_address(origin.hostname or "").is_loopback
    except ValueError:
        local = origin.hostname == "localhost"
    if (origin.scheme != "http" or not local or origin.username or origin.password
            or origin.query or origin.fragment or origin.path not in ("", "/")):
        raise MonitorError("Comfy URL must be a loopback HTTP origin")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", config["request_key"]):
        raise MonitorError("Invalid request key")
    if not Path(config["output"]).is_absolute():
        raise MonitorError("Output must be an absolute private path")
    if not 1 <= config["poll_seconds"] <= 30:
        raise MonitorError("Poll interval must be between one and thirty seconds")
    if not 0 < (parse_deadline(config["deadline_utc"]) - now).total_seconds() <= 14400:
        raise MonitorError("Deadline must be within the next four hours")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def get_json(config, endpoint, timeout):
    if endpoint not in ("/queue", "/history"):
        raise MonitorError("Read-only endpoint violation")
    request = Request(config["comfy_url"].rstrip("/") + endpoint, method="GET")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def task_identity(item):
    if not isinstance(item, (list, tuple)) or len(item) < 4:
        return None
    prompt_id, workflow, extra = item[1:4]
    if not isinstance(workflow, dict) or not isinstance(extra, dict):
        return None
    if not any(isinstance(node, dict) and node.get("class_type") == "WanImageToVideo"
               for node in workflow.values()):
        return None
    key = extra.get("aniflow_request_key")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
        return None
    if not isinstance(prompt_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", prompt_id):
        raise MonitorError("Invalid prompt identity")
    return {"prompt_id": prompt_id, "request_key": key}


def select_target(queue, history, request_key, bound=None):
    if not isinstance(queue, dict) or not isinstance(history, dict):
        raise MonitorError("Invalid Comfy response shape")
    if any(not isinstance(queue.get(key, []), list) for key in ("queue_running", "queue_pending")):
        raise MonitorError("Invalid Comfy queue shape")
    items = list(queue.get("queue_running", [])) + list(queue.get("queue_pending", []))
    items += [row.get("prompt") for row in history.values() if isinstance(row, dict)]
    candidates = {}
    for item in items:
        identity = task_identity(item)
        if identity and identity["request_key"] == request_key:
            candidates[identity["prompt_id"]] = identity
    if len(candidates) > 1:
        raise MonitorError("Multiple prompts for the same request key")
    selected = next(iter(candidates.values()), None)
    if bound and selected and selected != bound:
        raise MonitorError("Bound prompt identity changed")
    selected = bound or selected
    if selected and selected["prompt_id"] in history:
        job = history[selected["prompt_id"]]
        if not isinstance(job, dict) or task_identity(job.get("prompt")) != selected:
            raise MonitorError("History correlation changed")
    return selected


def execution_timing(job, prompt_id):
    status = job.get("status", {})
    if not isinstance(status, dict) or not isinstance(status.get("messages", []), list):
        raise MonitorError("Invalid Comfy execution status")
    events = {}
    errors = []
    for message in status.get("messages", []):
        if not isinstance(message, (list, tuple)) or len(message) != 2:
            continue
        kind, payload = message
        if kind not in ("execution_start", "execution_success", "execution_error", "execution_interrupted"):
            continue
        if not isinstance(payload, dict) or payload.get("prompt_id", prompt_id) != prompt_id:
            continue
        timestamp = payload.get("timestamp")
        if (type(timestamp) not in (int, float) or not math.isfinite(timestamp)
                or not 946684800000 <= timestamp < 4102444800000):
            errors.append("InvalidExecutionTimestamp")
            continue
        if kind in events and events[kind] != timestamp:
            errors.append("ConflictingExecutionTimestamp")
        events[kind] = timestamp
    terminal = [kind for kind in ("execution_success", "execution_error", "execution_interrupted")
                if kind in events]
    if len(terminal) > 1:
        errors.append("ConflictingTerminalEvents")
    ending = events.get(terminal[0]) if len(terminal) == 1 else None
    started = events.get("execution_start")
    if started is not None and ending is not None and ending < started:
        errors.append("ExecutionTimeReversed")
    elapsed = ((ending - started) / 1000
               if started is not None and ending is not None and not errors else None)
    completed = status.get("completed") is True
    outcome = ("success" if terminal == ["execution_success"] and completed
               and status.get("status_str") == "success" else
               "failed" if terminal and terminal != ["execution_success"] else None)
    return {"start_timestamp_ms": started, "terminal_timestamp_ms": ending,
            "terminal_event": terminal[0] if len(terminal) == 1 else None,
            "inference_elapsed_seconds": elapsed,
            "time_source": "ComfyUI execution messages in correlated history",
            "errors": sorted(set(errors)), "outcome": outcome}


def parse_gpu(text):
    rows = list(csv.reader(text.strip().splitlines()))
    if len(rows) != 1 or len(rows[0]) != 5:
        raise MonitorError("Expected one GPU telemetry row")
    index, name, used, total, utilization = (field.strip() for field in rows[0])
    values = [float(value) for value in (used, total, utilization)]
    if index != "0" or not all(math.isfinite(value) for value in values):
        raise MonitorError("Invalid GPU telemetry")
    if not 0 <= values[0] <= values[1] or values[1] <= 0 or not 0 <= values[2] <= 100:
        raise MonitorError("GPU telemetry outside valid range")
    return {"gpu_name": name, "gpu_memory_used_bytes": int(values[0] * 1024**2),
            "gpu_memory_total_bytes": int(values[1] * 1024**2), "gpu_utilization_percent": values[2]}


def parse_meminfo(text):
    fields = {}
    for line in text.splitlines():
        name, _, value = line.partition(":")
        if name in ("MemTotal", "MemAvailable"):
            number, unit = value.split()
            if unit != "kB":
                raise MonitorError("Unexpected memory unit")
            fields[name] = int(number) * 1024
    if not 0 <= fields["MemAvailable"] <= fields["MemTotal"] or fields["MemTotal"] <= 0:
        raise MonitorError("Invalid memory telemetry")
    return {"host_ram_total_bytes": fields["MemTotal"],
            "host_ram_used_bytes": fields["MemTotal"] - fields["MemAvailable"]}


def collect_host(timeout, run=subprocess.run, read_text=lambda path: Path(path).read_text()):
    result = {"gpu_memory_used_bytes": None, "host_ram_used_bytes": None,
              "gpu_processes": None, "errors": {}}
    try:
        response = run(["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                        "--format=csv,noheader,nounits"], capture_output=True, check=True,
                       text=True, timeout=timeout())
        result.update(parse_gpu(response.stdout))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, MonitorError) as exc:
        result["errors"]["gpu"] = type(exc).__name__
    try:
        result.update(parse_meminfo(read_text("/proc/meminfo")))
    except (OSError, ValueError, KeyError, MonitorError) as exc:
        result["errors"]["ram"] = type(exc).__name__
    try:
        response = run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                        "--format=csv,noheader,nounits"], capture_output=True, check=True,
                       text=True, timeout=timeout())
        processes = []
        for row in csv.reader(response.stdout.strip().splitlines()):
            if len(row) != 3:
                raise MonitorError("Invalid GPU process telemetry")
            pid, name, used = (field.strip() for field in row)
            if not pid.isdigit() or int(pid) <= 0:
                raise MonitorError("Invalid GPU process identity")
            process = {"pid": int(pid), "name": name, "gpu_memory_used_bytes": None,
                       "rss_bytes": None}
            try:
                value = float(used)
                if math.isfinite(value) and value >= 0:
                    process["gpu_memory_used_bytes"] = int(value * 1024**2)
                else:
                    process["memory_error"] = "InvalidProcessGpuMemory"
            except ValueError:
                process["memory_error"] = "UnavailableProcessGpuMemory"
            try:
                lines = read_text("/proc/" + pid + "/status").splitlines()
                rss = next(line.split()[1:3] for line in lines if line.startswith("VmRSS:"))
                if rss[1] != "kB" or int(rss[0]) < 0:
                    raise MonitorError("Invalid process RSS")
                process["rss_bytes"] = int(rss[0]) * 1024
            except (OSError, ValueError, IndexError, StopIteration, MonitorError) as exc:
                process["rss_error"] = type(exc).__name__
            processes.append(process)
        result["gpu_processes"] = processes
    except (OSError, ValueError, subprocess.SubprocessError, MonitorError) as exc:
        result["errors"]["processes"] = type(exc).__name__
    return result


def summarize(report):
    def maximum(rows, key):
        values = [row[key] for row in rows if row.get(key) is not None]
        return max(values) if values else None

    timing = report.get("execution") or {}
    start, end = timing.get("start_timestamp_ms"), timing.get("terminal_timestamp_ms")
    during = [row for row in report["samples"] if start is not None and end is not None
              and not timing.get("errors") and start <= row["timestamp_ms"] <= end]
    report.update(observed_gpu_vram_peak_bytes=maximum(report["samples"], "gpu_memory_used_bytes"),
                  observed_host_ram_peak_bytes=maximum(report["samples"], "host_ram_used_bytes"),
                  gpu_vram_peak_bytes=maximum(during, "gpu_memory_used_bytes"),
                  host_ram_peak_bytes=maximum(during, "host_ram_used_bytes"),
                  inference_elapsed_seconds=timing.get("inference_elapsed_seconds"))


def save_report(path, report):
    partial = path.with_suffix(path.suffix + ".tmp")
    if path.is_symlink() or partial.is_symlink():
        raise MonitorError("Telemetry symlink is not allowed")
    with partial.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    partial.chmod(0o600)
    partial.replace(path)


def monitor(config, get=None, sample=collect_host, now=utc_now,
            monotonic=time.monotonic, sleep=time.sleep):
    started = now()
    validate_config(config, started)
    output = Path(config["output"])
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.exists() or output.is_symlink():
        raise MonitorError("Existing telemetry must not be overwritten")
    lock = output.with_suffix(output.suffix + ".lock")
    handle = lock.open("x", encoding="utf-8")
    handle.close()
    deadline = parse_deadline(config["deadline_utc"])
    end_monotonic = monotonic() + (deadline - started).total_seconds()
    report = {"schema_version": 1, "request_key": config["request_key"], "selection": None,
              "started_at_utc": started.isoformat(), "deadline_utc": deadline.isoformat(),
              "poll_seconds": config["poll_seconds"], "state": "observing", "samples": [],
              "execution": None, "comfy_read_errors": [], "cost_usd": None,
              "real_video_verified": False, "generation_posts": 0,
              "peak_measurement": "Sampled device/host used memory; lower bound, not CUDA allocator peak"}

    def remaining():
        return min((deadline - now()).total_seconds(), end_monotonic - monotonic())

    def timeout():
        if remaining() <= 0:
            raise MonitorError("Telemetry deadline reached")
        return min(3, remaining())

    try:
        save_report(output, report)
        while remaining() > 0:
            taken = now()
            observation = sample(timeout)
            report["samples"].append({"at_utc": taken.isoformat(),
                                      "timestamp_ms": taken.timestamp() * 1000, **observation})
            try:
                fetch = get or (lambda endpoint, seconds: get_json(config, endpoint, seconds))
                queue = fetch("/queue", timeout())
                history = fetch("/history", timeout())
                selected = select_target(queue, history, config["request_key"], report["selection"])
                report["selection"] = selected
                job = history.get(selected["prompt_id"]) if selected else None
                if job:
                    report["execution"] = execution_timing(job, selected["prompt_id"])
                    outcome = report["execution"]["outcome"]
                    if outcome:
                        report["state"] = "execution_success_observed" if outcome == "success" else "execution_failed_observed"
            except (OSError, ValueError) as exc:
                report["comfy_read_errors"].append({"at_utc": now().isoformat(), "error_class": type(exc).__name__})
            summarize(report)
            report["observed_at_utc"] = now().isoformat()
            save_report(output, report)
            if report["state"] != "observing":
                return report
            sleep(max(0, min(config["poll_seconds"], remaining())))
        report["state"] = "deadline_reached"
        return report
    except MonitorError as exc:
        if remaining() <= 0:
            report["state"] = "deadline_reached"
            return report
        report.update(state="monitor_failed", error_class=type(exc).__name__)
        raise
    finally:
        summarize(report)
        report["ended_at_utc"] = now().isoformat()
        save_report(output, report)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--request-key", required=True)
    parser.add_argument("--deadline-utc", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--poll-seconds", type=float, default=5)
    try:
        report = monitor(vars(parser.parse_args()))
        return 0 if report["state"] == "execution_success_observed" else 1
    except (MonitorError, OSError, ValueError) as exc:
        print("WAN_MONITOR_STOPPED:" + type(exc).__name__, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
