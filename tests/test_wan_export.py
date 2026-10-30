"""Observer/export tests use simulated jobs, never real GPU generation."""

import importlib.util
import json
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "wan_export", Path(__file__).parents[1] / "infra/ec2/wan_export.py")
wan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wan)


def task(prompt_id="prompt-one", key="request_123", model="WanImageToVideo"):
    return [1, prompt_id, {"1": {"class_type": model}}, {"aniflow_request_key": key}]


@pytest.fixture
def config(tmp_path):
    return {"region": "us-east-2", "bucket": "test-private-bucket",
            "experiment_id": "aniflow-wan-ohio-20261027-test",
            "comfy_url": "http://127.0.0.1:8188", "output_root": str(tmp_path),
            "deadline_utc": (wan.utc_now() + timedelta(hours=1)).isoformat(),
            "ffmpeg_path": str(Path(shutil.which("ffmpeg") or __file__).resolve()),
            "ffprobe_path": str(Path(shutil.which("ffprobe") or __file__).resolve())}


def test_select_single_correlated_task_deduplicates_queue_history():
    candidate = task()
    assert wan.select_task({"queue_running": [candidate]},
                           {"prompt-one": {"prompt": candidate}}) == {
                               "prompt_id": "prompt-one", "request_key": "request_123"}


@pytest.mark.parametrize("candidate", [task(model="Wan22ImageToVideoLatent"),
                                      task(model="H3ImageToVideo"), task(key="short")])
def test_wrong_model_or_missing_correlation_is_not_selected(candidate):
    assert wan.select_task({"queue_pending": [candidate]}, {}) is None


def test_multiple_targets_and_conflicting_correlation_fail_closed():
    for second in (task("prompt-two"), task(key="another_key")):
        with pytest.raises(wan.ExportError, match="Ambiguous"):
            wan.select_task({"queue_pending": [task(), second]}, {})


@pytest.mark.parametrize("filename,folder", [("../outside.mp4", ""),
                                             ("/outside.mp4", ""),
                                             ("C:\\outside.mp4", ""),
                                             ("ok.mp4", "../"),
                                             ("ok.mp4", "C:\\outside")])
def test_output_paths_cannot_escape(tmp_path, filename, folder):
    job = {"outputs": {"1": {"video": [{"filename": filename,
                                        "subfolder": folder, "type": "output"}]}}}
    with pytest.raises(wan.ExportError, match="escape"):
        wan.source_path(job, tmp_path)


def test_output_symlink_escape_is_rejected(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.mp4")
    outside.write_bytes(b"outside")
    try:
        (tmp_path / "linked.mp4").symlink_to(outside)
    except OSError:
        pytest.skip("Symlink permission unavailable")
    job = {"outputs": [{"filename": "linked.mp4", "type": "output"}]}
    try:
        with pytest.raises(wan.ExportError, match="escape"):
            wan.source_path(job, tmp_path)
    finally:
        outside.unlink()


def test_unique_output_only(tmp_path):
    video = tmp_path / "one.mp4"
    video.write_bytes(b"video")
    item = {"filename": "one.mp4", "type": "output"}
    assert wan.source_path({"outputs": [item]}, tmp_path) == video
    for outputs in ([], [item, item], [{**item, "type": "temp"}]):
        with pytest.raises(wan.ExportError, match="exactly one"):
            wan.source_path({"outputs": outputs}, tmp_path)


@pytest.mark.parametrize("field,value", [("region", "ap-northeast-1"),
                                        ("experiment_id", "other"),
                                        ("comfy_url", "http://example.com:8188"),
                                        ("comfy_url", "http://127.0.0.1:8188/prompt"),
                                        ("comfy_url", "http://user@localhost:8188"),
                                        ("deadline_utc", "2026-10-27T00:00:00")])
def test_config_rejects_wrong_scope(config, field, value):
    with pytest.raises(wan.ExportError):
        wan.validate_config({**config, field: value})


def test_http_is_get_only_and_fixed_paths(config, monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"queue_running": []}'

    def open_url(url, timeout):
        seen.append(url)
        assert 0 < timeout <= 15
        return Response()

    monkeypatch.setattr(wan, "urlopen", open_url)
    assert wan.get_json(config, "/queue") == {"queue_running": []}
    with pytest.raises(wan.ExportError, match="Read-only"):
        wan.get_json(config, "/prompt")
    assert seen == ["http://127.0.0.1:8188/queue"]


def test_bad_video_specs_fail_before_decode(config, tmp_path, monkeypatch):
    path = tmp_path / "fake.mp4"
    path.write_bytes(b"\x00\x00\x00\x20ftypisom")
    video = {"codec_type": "video", "width": 800, "height": 1376, "avg_frame_rate": "24/1",
             "nb_read_frames": "121", "duration": "5.041667", "sample_aspect_ratio": "1:1"}
    calls = []

    def probe(config, args):
        calls.append(args)
        return SimpleNamespace(stdout=json.dumps({"streams": [video],
                                                 "format": {"duration": "5.041667"}}))

    monkeypatch.setattr(wan, "run_media", probe)
    for field, wrong in (("width", 774), ("height", 1280), ("nb_read_frames", "120"),
                         ("avg_frame_rate", "16/1")):
        original = video[field]
        video[field] = wrong
        with pytest.raises(wan.ExportError, match="specification"):
            wan.verify_media(config, path)
        video[field] = original
    assert len(calls) == 4


class S3:
    def __init__(self, fail_key=None):
        self.calls = []
        self.fail_key = fail_key

    def put_object(self, **kwargs):
        body = kwargs.pop("Body").read()
        self.calls.append({**kwargs, "bytes": body})
        if self.fail_key and kwargs["Key"].endswith(self.fail_key):
            raise OSError("simulated network failure")


def test_upload_retries_same_object_with_private_encryption_then_resumes(config, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic-video")
    receipt_path = tmp_path / "receipt.json"
    receipt = {}
    client = S3("source.mp4")
    with pytest.raises(wan.ExportError, match="exhausted"):
        wan.upload(config, client, source, "fixed/source.mp4", receipt, receipt_path,
                   sleep=lambda _: None)
    assert len(client.calls) == 3
    restored = json.loads(receipt_path.read_text())
    with pytest.raises(wan.ExportError, match="exhausted"):
        wan.upload(config, client, source, "fixed/source.mp4", restored, receipt_path)
    assert len(client.calls) == 3
    assert all(call["ServerSideEncryption"] == "AES256" for call in client.calls)
    assert all(call["Metadata"]["sha256"] == wan.fingerprint(source)["sha256"]
               for call in client.calls)


def test_deadline_blocks_http_and_upload(config, tmp_path, monkeypatch):
    config["deadline_utc"] = (wan.utc_now() - timedelta(seconds=1)).isoformat()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic")
    client = S3()
    monkeypatch.setattr(wan, "urlopen", lambda *a, **kw: pytest.fail("Late HTTP call"))
    with pytest.raises(wan.Deadline):
        wan.get_json(config, "/queue")
    with pytest.raises(wan.Deadline):
        wan.upload(config, client, source, "fixed/source.mp4", {}, tmp_path / "receipt.json")
    assert not client.calls


def test_single_process_lock(tmp_path):
    with wan.process_lock(tmp_path / "lock"), pytest.raises(wan.ExportError, match="Another"):  # noqa: SIM117 -- Keep the first lock held while checking contention.
        with wan.process_lock(tmp_path / "lock"):
            pytest.fail("Second lock acquired")
    with wan.process_lock(tmp_path / "lock"):
        pass


def test_restart_follows_persisted_task_and_partial_uploads(config, tmp_path, monkeypatch):
    state = tmp_path / ".aniflow-export" / config["experiment_id"]
    state.mkdir(parents=True)
    source, final = tmp_path / "source.mp4", state / "prompt-one.mp4"
    source.write_bytes(b"source-synthetic")
    final.write_bytes(b"final-synthetic")
    receipt = {"selection": {"prompt_id": "prompt-one", "request_key": "request_123"},
               "observed_at_utc": wan.utc_now().isoformat(), "source_path": str(source),
               "observed_elapsed_seconds": 10,
               "media": {"source": {**wan.fingerprint(source), "metadata": {}},
                         "final": {**wan.fingerprint(final), "metadata": {}}}}
    receipt_path = state / "receipt.json"
    prefix = "experiments/" + config["experiment_id"]
    client = S3()
    wan.upload(config, client, source, prefix + "/outputs/prompt-one.source.mp4", receipt,
               receipt_path)
    monkeypatch.setattr(wan, "verify_media", lambda *a, **k: pytest.fail("Repeated media work"))
    result = wan.observe(config, client, get=lambda *a: pytest.fail("Restart polled another job"))
    assert result["complete"]
    assert len(client.calls) == 3
    with pytest.raises(wan.ExportError, match="configuration changed"):
        wan.observe({**config, "bucket": "different-private-bucket"}, client)
    manifest = json.loads(client.calls[-1]["bytes"])
    assert manifest["model"] == "wan2.2-i2v-a14b"
    assert manifest["gpu_vram_peak_bytes"] is None
    assert manifest["inference_elapsed_seconds"] is None
    assert manifest["cost_usd"] is None
    wan.observe(config, client, get=lambda *a: pytest.fail("Completed task polled"))
    assert len(client.calls) == 3


def test_persisted_selection_never_switches_to_second_job(config, tmp_path):
    state = tmp_path / ".aniflow-export" / config["experiment_id"]
    state.mkdir(parents=True)
    wan.save_receipt(state / "receipt.json", {
        "selection": {"prompt_id": "prompt-one", "request_key": "request_123"},
        "observed_at_utc": wan.utc_now().isoformat()})
    history = {"prompt-one": {"prompt": task(),
                              "status": {"completed": False, "status_str": "error"}},
               "prompt-two": {"prompt": task("prompt-two"),
                              "status": {"completed": True, "status_str": "success"}}}
    calls = []

    def get(config, endpoint):
        calls.append(endpoint)
        return history if endpoint == "/history" else {"queue_running": [task("prompt-two")]}

    with pytest.raises(wan.ExportError, match="failed; no resubmission"):
        wan.observe(config, S3(), get=get)
    assert calls == ["/queue", "/history"]
    assert json.loads((state / "receipt.json").read_text())["selection"]["prompt_id"] == "prompt-one"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="Local FFmpeg tools unavailable")
def test_synthetic_media_full_decode_crop_and_exact_five_seconds(config, tmp_path):
    # This is a CPU-generated color fixture, not evidence of successful GPU inference.
    source, final = tmp_path / "synthetic.mp4", tmp_path / "final.mp4"
    subprocess.run([config["ffmpeg_path"], "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=800x1376:r=24", "-frames:v", "121", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source)],
                   check=True, timeout=60)
    assert wan.verify_media(config, source)["frame_count"] == 121
    metadata = wan.postprocess(config, source, final)
    assert metadata == {"width": 774, "height": 1376, "fps": 24.0, "frame_count": 120,
                        "duration_seconds": 5.0, "sample_aspect_ratio": "1:1"}
    with pytest.raises((wan.ExportError, subprocess.CalledProcessError)):
        wan.verify_media(config, final)
    job = {"prompt": task(), "status": {"completed": True, "status_str": "success"},
           "outputs": {"1": [{"filename": source.name, "subfolder": "", "type": "output"}]}}
    client = S3()
    calls = []

    def get(config, endpoint):
        calls.append(endpoint)
        return {"prompt-one": job} if endpoint == "/history" else {}

    receipt = wan.observe(config, client, get=get)
    assert receipt["complete"]
    assert calls == ["/queue", "/history"]
    prefix = "experiments/" + config["experiment_id"]
    assert [call["Key"] for call in client.calls] == [
        prefix + "/outputs/prompt-one.source.mp4", prefix + "/outputs/prompt-one.mp4",
        prefix + "/reports/prompt-one.json"]
    manifest = json.loads(client.calls[-1]["bytes"])
    assert manifest["media"]["final"]["metadata"]["frame_count"] == 120
    assert manifest["media"]["source"]["sha256"] == wan.fingerprint(source)["sha256"]
