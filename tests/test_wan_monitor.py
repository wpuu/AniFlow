"""Synthetic telemetry tests only; no GPU, network, media generation or AWS calls."""
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "wan_monitor", Path(__file__).parents[1] / "infra/ec2/wan_monitor.py")
wan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wan)
START = datetime(2026, 10, 29, tzinfo=UTC)
START_MS = START.timestamp() * 1000
KEY = "request_cat_123"


def task(prompt_id="prompt-one", key=KEY):
    return [1, prompt_id, {"1": {"class_type": "WanImageToVideo"}},
            {"aniflow_request_key": key}]


def job(start=START_MS, end=START_MS + 10000, outcome="execution_success"):
    return {"prompt": task(), "status": {"completed": True,
            "status_str": "success" if outcome == "execution_success" else "error",
            "messages": [["execution_start", {"prompt_id": "prompt-one", "timestamp": start}],
                         [outcome, {"prompt_id": "prompt-one", "timestamp": end}]]}}


class Clock:
    def __init__(self):
        self.elapsed = 0

    def now(self):
        return START + timedelta(seconds=self.elapsed)

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds


@pytest.fixture
def config(tmp_path):
    return {"comfy_url": "http://127.0.0.1:8188", "request_key": KEY,
            "deadline_utc": (START + timedelta(seconds=20)).isoformat(),
            "poll_seconds": 5, "output": str(tmp_path / "telemetry.json")}


@pytest.mark.parametrize("field,value", [("comfy_url", "http://example.com:8188"),
                                        ("comfy_url", "https://localhost:8188"),
                                        ("comfy_url", "http://user@localhost:8188"),
                                        ("comfy_url", "http://127.0.0.1:8188/prompt"),
                                        ("request_key", "short"), ("output", "relative.json"),
                                        ("deadline_utc", "2026-10-29T00:00:00"),
                                        ("deadline_utc", "2026-10-29T05:00:00Z"),
                                        ("poll_seconds", 0)])
def test_invalid_config_rejected(config, field, value):
    with pytest.raises(wan.MonitorError):
        wan.validate_config({**config, field: value}, START)


def test_only_requested_task_selected_and_queue_history_deduplicated():
    assert wan.select_target({"queue_running": [task(), task("other", "other_key_123")]},
                             {"prompt-one": job()}, KEY) == {
                                 "prompt_id": "prompt-one", "request_key": KEY}
    assert wan.select_target({"queue_running": [task(key="other_key_123")]}, {}, KEY) is None


def test_duplicate_key_or_changed_history_fails_closed():
    with pytest.raises(wan.MonitorError, match="Multiple"):
        wan.select_target({"queue_running": [task(), task("second")]}, {}, KEY)
    with pytest.raises(wan.MonitorError, match="correlation"):
        wan.select_target({}, {"prompt-one": {"prompt": task(key="other_key_123")}}, KEY,
                          {"prompt_id": "prompt-one", "request_key": KEY})
    with pytest.raises(wan.MonitorError, match="identity"):
        wan.select_target({"queue_running": [task("second")]}, {}, KEY,
                          {"prompt_id": "prompt-one", "request_key": KEY})


def test_event_derived_duration_does_not_use_observer_time():
    result = wan.execution_timing(job(), "prompt-one")
    assert result["inference_elapsed_seconds"] == 10
    assert result["outcome"] == "success"
    missing = job()
    missing["status"]["messages"] = []
    assert wan.execution_timing(missing, "prompt-one")["inference_elapsed_seconds"] is None


@pytest.mark.parametrize("start,end", [(0, START_MS), (True, START_MS),
                                     (START_MS, START_MS - 1), (START_MS, float("nan")),
                                     (START_MS / 1000, START_MS / 1000 + 1)])
def test_invalid_or_reversed_event_time_stays_unknown(start, end):
    result = wan.execution_timing(job(start, end), "prompt-one")
    assert result["inference_elapsed_seconds"] is None
    assert result["errors"]


def test_execution_failure_recorded_without_video_success_claim():
    result = wan.execution_timing(job(outcome="execution_error"), "prompt-one")
    assert result["outcome"] == "failed"
    assert result["inference_elapsed_seconds"] == 10


def test_gpu_parser_and_real_proc_units():
    gpu = wan.parse_gpu("0, NVIDIA L4, 22000, 23034, 98\n")
    assert gpu["gpu_memory_used_bytes"] == 22000 * 1024**2
    assert gpu["gpu_utilization_percent"] == 98
    assert wan.parse_meminfo("MemTotal: 1000 kB\nMemAvailable: 250 kB\n") == {
        "host_ram_total_bytes": 1024000, "host_ram_used_bytes": 768000}


def test_sampling_failures_are_unknown_with_error_classes():
    def missing(*args, **kwargs):
        raise FileNotFoundError("not exposed")

    result = wan.collect_host(lambda: 3, run=missing, read_text=missing)
    assert result["gpu_memory_used_bytes"] is None and result["host_ram_used_bytes"] is None
    assert result["gpu_processes"] is None
    assert set(result["errors"].values()) == {"FileNotFoundError"}


def test_process_rss_and_gpu_memory_are_separate_actual_units():
    def run(args, **kwargs):
        return SimpleNamespace(stdout="0, NVIDIA L4, 100, 23034, 0\n" if "--query-gpu=" in args[1]
                               else "45, python, 90\n")

    def read(path):
        return "MemTotal: 1000 kB\nMemAvailable: 200 kB\n" if path == "/proc/meminfo" else "VmRSS: 300 kB\n"

    result = wan.collect_host(lambda: 3, run=run, read_text=read)
    assert result["gpu_processes"] == [{"pid": 45, "name": "python",
                                        "gpu_memory_used_bytes": 90 * 1024**2,
                                        "rss_bytes": 300 * 1024}]


def test_monitor_preserves_samples_and_only_event_window_peak(config):
    clock = Clock()

    def get(endpoint, timeout):
        assert endpoint in ("/queue", "/history") and 0 < timeout <= 3
        if endpoint == "/queue":
            return {"queue_running": [task()]}
        return {"prompt-one": job(START_MS + 1000, START_MS + 10000)} if clock.elapsed >= 10 else {}

    def sample(timeout):
        return {"gpu_memory_used_bytes": 999 if clock.elapsed == 0 else int(clock.elapsed),
                "host_ram_used_bytes": 50, "errors": {}}

    report = wan.monitor(config, get=get, sample=sample, now=clock.now,
                         monotonic=clock.monotonic, sleep=clock.sleep)
    assert report["state"] == "execution_success_observed"
    assert report["observed_gpu_vram_peak_bytes"] == 999
    assert report["gpu_vram_peak_bytes"] == 10
    assert report["inference_elapsed_seconds"] == 9
    assert len(report["samples"]) == 3
    assert report["cost_usd"] is None and report["real_video_verified"] is False
    assert report["generation_posts"] == 0
    assert json.loads(Path(config["output"]).read_text())["state"] == report["state"]
    assert not Path(config["output"] + ".lock").exists()
    with pytest.raises(wan.MonitorError, match="overwritten"):
        wan.monitor(config, get=get, sample=sample, now=clock.now,
                    monotonic=clock.monotonic, sleep=clock.sleep)


def test_network_failures_until_fixed_deadline_never_generate_zero_peaks(config):
    clock = Clock()

    def get(endpoint, timeout):
        raise OSError("server message not persisted")

    report = wan.monitor(config, get=get, sample=lambda _: {"errors": {"gpu": "Error"}},
                         now=clock.now, monotonic=clock.monotonic, sleep=clock.sleep)
    assert report["state"] == "deadline_reached" and clock.elapsed == 20
    assert report["gpu_vram_peak_bytes"] is None
    assert report["observed_gpu_vram_peak_bytes"] is None
    assert report["inference_elapsed_seconds"] is None
    assert all(row["error_class"] == "OSError" for row in report["comfy_read_errors"])


def test_ambiguous_task_saves_failed_report_and_stops(config):
    clock = Clock()

    def get(endpoint, timeout):
        return {"queue_running": [task(), task("second")]} if endpoint == "/queue" else {}

    with pytest.raises(wan.MonitorError):
        wan.monitor(config, get=get, sample=lambda _: {}, now=clock.now,
                    monotonic=clock.monotonic, sleep=clock.sleep)
    saved = json.loads(Path(config["output"]).read_text())
    assert saved["state"] == "monitor_failed"
    assert saved["error_class"] == "MonitorError"
    assert saved["real_video_verified"] is False


def test_http_request_is_get_only_and_does_not_follow_redirects(config, monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{}'

    def opener(*handlers):
        assert any(isinstance(handler, wan.NoRedirect) for handler in handlers)
        return SimpleNamespace(open=lambda request, timeout: requests.append(request) or Response())

    monkeypatch.setattr(wan, "build_opener", opener)
    assert wan.get_json(config, "/history", 1) == {}
    assert requests[0].get_method() == "GET"
    with pytest.raises(wan.MonitorError, match="Read-only"):
        wan.get_json(config, "/prompt", 1)
