import hashlib
import importlib.util
import io
import json
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

import pytest


def module():
    path = Path(__file__).parents[1] / "infra/workspaces/gr6_export_result.py"
    spec = importlib.util.spec_from_file_location("gr6_export_result", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def setup_export(tmp_path):
    root = tmp_path / "output"
    root.mkdir()
    video = root / "real.mp4"
    video.write_bytes(b"synthetic-test-bytes-not-a-real-video")
    config = {
        "prompt_id": "only-job", "comfy_url": "http://127.0.0.1:8188",
        "output_root": str(root), "deadline_utc": "2099-01-01T00:00:00Z",
        "expected_width": 1280, "expected_height": 720, "ffprobe_path": "ffprobe.exe",
        "video_put_url": "https://private.s3.ap-northeast-1.amazonaws.com/outputs/real.mp4"
                         "?X-Amz-Signature=SECRET&X-Amz-Credential=SECRET",
        "manifest_put_url": "https://private.s3.ap-northeast-1.amazonaws.com/reports/manifest.json"
                            "?X-Amz-Signature=SECRET&X-Amz-Credential=SECRET",
    }
    path = tmp_path / "private-config.json"
    path.write_text(json.dumps(config))
    history = {"only-job": {
        "status": {"completed": True, "status_str": "success"},
        "outputs": {"save": {"videos": [
            {"filename": "real.mp4", "subfolder": "", "type": "output"}]}}}}
    return path, config, history, video


def fake_probe(monkeypatch, worker, *, duration=5, width=1280):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps({
        "streams": [{"codec_type": "video", "width": width, "height": 720}],
        "format": {"duration": str(duration)},
    })))
    monkeypatch.setattr(worker.subprocess, "run", run)
    return run


def fake_http(monkeypatch, worker, histories, uploads, fail_video=False, fail_manifest=False):
    pending = iter(histories)

    def request(req, timeout):
        assert timeout > 0
        if req.method == "GET":
            assert req.full_url == "http://127.0.0.1:8188/history/only-job"
            return io.BytesIO(json.dumps(next(pending)).encode())
        assert req.method == "PUT"
        kind = "video" if "/outputs/" in req.full_url else "manifest"
        if (kind == "video" and fail_video) or (kind == "manifest" and fail_manifest):
            raise URLError("SECRET private signed URL")
        data = req.data.read() if hasattr(req.data, "read") else req.data
        uploads.append((kind, data))
        response = io.BytesIO(b"")
        response.status = 200
        return response

    monkeypatch.setattr(worker, "open_request", request)
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)


def test_unknown_job_waits_only_for_configured_id_and_success_receipt_prevents_reupload(
    setup_export, monkeypatch,
):
    worker = module()
    path, _, history, video = setup_export
    uploads = []
    fake_probe(monkeypatch, worker)
    fake_http(monkeypatch, worker, [{"unrelated-job": history["only-job"]}, history], uploads)
    receipt = worker.export(path)
    assert receipt["state"] == "SAVED"
    assert receipt["sha256"] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert receipt["bytes"] == video.stat().st_size
    assert [kind for kind, _ in uploads] == ["video", "manifest"]
    assert json.loads(uploads[1][1])["sha256"] == receipt["sha256"]
    assert "SECRET" not in json.dumps(receipt)
    monkeypatch.setattr(worker, "open_request", Mock(side_effect=AssertionError("Network forbidden")))
    assert worker.export(path) == receipt


def test_comfy_failure_never_probes_or_uploads(setup_export, monkeypatch):
    worker = module()
    path, _, history, _ = setup_export
    history["only-job"]["status"].update(status_str="error", completed=False)
    uploads = []
    probe = fake_probe(monkeypatch, worker)
    fake_http(monkeypatch, worker, [history], uploads)
    with pytest.raises(worker.ExportError, match="COMFY_JOB_FAILED"):
        worker.export(path)
    probe.assert_not_called()
    assert uploads == []


@pytest.mark.parametrize("folder", ["../escape", "C:\\outside"])
def test_traversal_is_rejected_before_probe_or_upload(setup_export, monkeypatch, folder):
    worker = module()
    path, _, history, _ = setup_export
    outside = path.parent / "escape"
    outside.mkdir()
    (outside / "real.mp4").write_bytes(b"outside")
    history["only-job"]["outputs"]["save"]["videos"][0]["subfolder"] = folder
    probe = fake_probe(monkeypatch, worker)
    uploads = []
    fake_http(monkeypatch, worker, [history], uploads)
    with pytest.raises(worker.ExportError, match="OUTPUT_PATH_ESCAPE"):
        worker.export(path)
    probe.assert_not_called()
    assert not uploads


def test_symlink_escape_is_rejected(setup_export):
    worker = module()
    path, config, history, _ = setup_export
    outside = path.parent / "external"
    outside.mkdir()
    (outside / "real.mp4").write_bytes(b"outside")
    link = Path(config["output_root"]) / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                       capture_output=True, text=True, check=True)
    history["only-job"]["outputs"]["save"]["videos"][0]["subfolder"] = "link"
    with pytest.raises(worker.ExportError, match="OUTPUT_PATH_ESCAPE"):
        worker.completed_video(history, "only-job", Path(config["output_root"]))


@pytest.mark.parametrize("probe_result", ["failure", "wrong-duration", "wrong-size"])
def test_probe_failure_or_wrong_spec_prevents_upload(setup_export, monkeypatch, probe_result):
    worker = module()
    path, _, history, _ = setup_export
    fake_probe(monkeypatch, worker, duration=6 if probe_result == "wrong-duration" else 5,
               width=640 if probe_result == "wrong-size" else 1280)
    if probe_result == "failure":
        monkeypatch.setattr(worker.subprocess, "run", Mock(side_effect=
            subprocess.CalledProcessError(1, ["ffprobe.exe"], stderr="sensitive local path")))
    uploads = []
    fake_http(monkeypatch, worker, [history], uploads)
    with pytest.raises(worker.ExportError, match="FFPROBE_FAILED|VIDEO_SPEC_MISMATCH"):
        worker.export(path)
    assert not uploads


def test_failed_upload_has_bounded_retry_and_no_secret_in_error(setup_export, monkeypatch):
    worker = module()
    path, _, history, _ = setup_export
    fake_probe(monkeypatch, worker)
    fake_http(monkeypatch, worker, [history], [], fail_video=True)
    wrapped = Mock(wraps=worker.open_request)
    monkeypatch.setattr(worker, "open_request", wrapped)
    with pytest.raises(worker.ExportError) as error:
        worker.export(path)
    assert str(error.value) == "UPLOAD_FAILED" and wrapped.call_count == 4


def test_manifest_failure_resumes_without_history_probe_or_video_put(setup_export, monkeypatch):
    worker = module()
    path, _, history, _ = setup_export
    fake_probe(monkeypatch, worker)
    uploads = []
    fake_http(monkeypatch, worker, [history], uploads, fail_manifest=True)
    with pytest.raises(worker.ExportError, match="UPLOAD_FAILED"):
        worker.export(path)
    assert [kind for kind, _ in uploads] == ["video"]
    fake_http(monkeypatch, worker, [], uploads)
    monkeypatch.setattr(worker.subprocess, "run", Mock(side_effect=AssertionError("Probe forbidden")))
    assert worker.export(path)["state"] == "SAVED"
    assert [kind for kind, _ in uploads] == ["video", "manifest"]


def test_expired_deadline_never_contacts_comfy(setup_export, monkeypatch):
    worker = module()
    path, config, _, _ = setup_export
    config["deadline_utc"] = "2000-01-01T00:00:00Z"
    path.write_text(json.dumps(config))
    network = Mock(side_effect=AssertionError("Network forbidden"))
    monkeypatch.setattr(worker, "open_request", network)
    with pytest.raises(worker.ExportError, match="DEADLINE_REACHED"):
        worker.export(path)
    network.assert_not_called()


def test_concurrent_or_crashed_export_lock_requires_reconciliation(setup_export):
    worker = module()
    path, _, _, _ = setup_export
    (path.parent / "h3-export-only-job.receipt.lock").write_text("existing exporter")
    with pytest.raises(worker.ExportError, match="EXPORT_LOCKED"):
        worker.export(path)


def test_streaming_upload_checks_deadline_before_read():
    worker = module()
    source = Mock()
    with pytest.raises(worker.ExportError, match="DEADLINE_REACHED"):
        worker.DeadlineReader(source, time.time() - 1).read(1024)
    source.read.assert_not_called()


def test_multiple_mp4_outputs_are_ambiguous_and_not_uploaded(setup_export, monkeypatch):
    worker = module()
    path, _, history, _ = setup_export
    history["only-job"]["outputs"]["save"]["videos"].append(
        {"filename": "second.mp4", "subfolder": "", "type": "output"})
    uploads = []
    fake_http(monkeypatch, worker, [history], uploads)
    with pytest.raises(worker.ExportError, match="EXPECTED_EXACTLY_ONE_MP4"):
        worker.export(path)
    assert not uploads


def test_empty_mp4_is_never_uploaded(setup_export, monkeypatch):
    worker = module()
    path, _, history, video = setup_export
    video.write_bytes(b"")
    uploads = []
    fake_http(monkeypatch, worker, [history], uploads)
    with pytest.raises(worker.ExportError, match="MP4_MISSING_OR_EMPTY"):
        worker.export(path)
    assert not uploads


def test_remote_comfy_url_cannot_be_used(setup_export):
    worker = module()
    path, config, _, _ = setup_export
    config["comfy_url"] = "http://example.com:8188"
    path.write_text(json.dumps(config))
    with pytest.raises(worker.ExportError, match="COMFY_MUST_BE_LOOPBACK"):
        worker.export(path)
