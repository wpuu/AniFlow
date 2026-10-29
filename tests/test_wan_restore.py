"""Offline S3 fixtures and CPU synthetic media only; no real Wan inference or AWS calls."""

import hashlib
import io
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from aniflow.studio import wan_restore as restore


class OfflineS3:
    def __init__(self, content=b"offline fixture, not a video"):
        self.meta = SimpleNamespace(region_name="us-east-2")
        self.content = content
        self.report = {"experiment_id": "aniflow-wan-ohio-20261027-test",
                       "model": "wan2.2-i2v-a14b", "prompt_id": "prompt-one",
                       "request_key": "request_123", "media": {"final": {
                           "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                           "metadata": dict(restore.FINAL_SPEC)}}}
        self.calls = []
        self.video_body = None

    def get_object(self, *, Bucket, Key):
        self.calls.append((Bucket, Key))
        if Key.endswith(".json"):
            data = json.dumps(self.report).encode()
            return {"Body": io.BytesIO(data), "ContentLength": len(data)}
        assert Key.endswith("/outputs/prompt-one.mp4")
        return {"Body": self.video_body or io.BytesIO(self.content),
                "ContentLength": len(self.content)}


@pytest.fixture
def arguments(tmp_path):
    return {"region": "us-east-2", "bucket": "test-private-bucket",
            "experiment_id": "aniflow-wan-ohio-20261027-test", "prompt_id": "prompt-one",
            "request_key": "request_123", "destination": tmp_path / "restored.mp4"}


@pytest.fixture
def offline_decode(monkeypatch):
    calls = []

    def verify(path, profile):
        calls.append((path, profile))
        assert path.is_file()
        assert profile == "wan_native_final"
        return {**restore.FINAL_SPEC, "audio_present": False}

    monkeypatch.setattr(restore, "verify_mp4", verify)
    return calls


def test_exact_report_and_final_get_then_full_local_verification(arguments, offline_decode):
    client = OfflineS3()
    digest, size, metadata = restore.restore_wan_output(client, **arguments)
    assert arguments["destination"].read_bytes() == client.content
    assert (digest, size) == (hashlib.sha256(client.content).hexdigest(), len(client.content))
    assert metadata["frame_count"] == 120
    prefix = "experiments/" + arguments["experiment_id"]
    assert client.calls == [(arguments["bucket"], prefix + "/reports/prompt-one.json"),
                            (arguments["bucket"], prefix + "/outputs/prompt-one.mp4")]
    assert len(offline_decode) == 1 and offline_decode[0][0].suffix == ".partial"
    assert not list(arguments["destination"].parent.glob("*.partial"))


def test_restart_reuses_existing_only_after_hash_and_decode(arguments, offline_decode):
    client = OfflineS3()
    restore.restore_wan_output(client, **arguments)
    first = arguments["destination"].read_bytes()
    client.calls.clear()
    restore.restore_wan_output(client, **arguments)
    assert arguments["destination"].read_bytes() == first
    assert len(client.calls) == 1 and client.calls[0][1].endswith(".json")
    assert len(offline_decode) == 2
    assert offline_decode[-1][0] == arguments["destination"]


@pytest.mark.parametrize("field,value", [("region", "us-east-1"),
                                        ("bucket", "bad/bucket"),
                                        ("experiment_id", "aniflow-h3-test"),
                                        ("experiment_id", "aniflow-wan-ohio-20261027-../test"),
                                        ("prompt_id", "../other"),
                                        ("request_key", "short")])
def test_invalid_scope_has_no_s3_reads(arguments, field, value):
    client = OfflineS3()
    with pytest.raises(ValueError):
        restore.restore_wan_output(client, **{**arguments, field: value})
    assert client.calls == []


def test_wrong_client_region_is_rejected_before_any_get(arguments):
    client = OfflineS3()
    client.meta.region_name = "us-west-2"
    with pytest.raises(ValueError, match="Ohio"):
        restore.restore_wan_output(client, **arguments)
    assert client.calls == []


@pytest.mark.parametrize("field,value", [("experiment_id", "another-experiment"),
                                        ("model", "hunyuan-video"),
                                        ("prompt_id", "another-prompt"),
                                        ("request_key", "another_key")])
def test_report_identity_mismatch_never_reads_video(arguments, field, value):
    client = OfflineS3()
    client.report[field] = value
    with pytest.raises(ValueError, match="identity"):
        restore.restore_wan_output(client, **arguments)
    assert len(client.calls) == 1
    assert not arguments["destination"].exists()


@pytest.mark.parametrize("field,value", [("bytes", True), ("bytes", 0),
                                        ("bytes", 1024**3 + 1), ("sha256", "invalid"),
                                        ("metadata", {**restore.FINAL_SPEC, "fps": 16}),
                                        ("metadata", {**restore.FINAL_SPEC, "frame_count": 121}),
                                        ("metadata", {**restore.FINAL_SPEC, "width": 800}),
                                        ("metadata", {**restore.FINAL_SPEC, "duration_seconds": 6}),
                                        ("metadata", {**restore.FINAL_SPEC,
                                                      "sample_aspect_ratio": "0:1"})])
def test_invalid_manifest_rejected_before_video_get(arguments, field, value):
    client = OfflineS3()
    client.report["media"]["final"][field] = value
    with pytest.raises(ValueError):
        restore.restore_wan_output(client, **arguments)
    assert len(client.calls) == 1


def test_report_size_is_bounded_before_read(arguments, monkeypatch):
    client = OfflineS3()
    body = io.BytesIO(b"oversized report fixture")
    monkeypatch.setattr(client, "get_object", lambda **_: {
        "Body": body, "ContentLength": restore.MAX_REPORT_BYTES + 1})
    with pytest.raises(ValueError, match="report length"):
        restore.restore_wan_output(client, **arguments)
    assert body.closed


@pytest.mark.parametrize("change", ["hash", "truncated", "overlong", "header"])
def test_corrupt_download_never_publishes_and_cleans_partial(arguments, offline_decode, change):
    client = OfflineS3()
    if change == "hash":
        client.report["media"]["final"]["sha256"] = "0" * 64
    elif change == "header":
        client.report["media"]["final"]["bytes"] += 1
    else:
        content = client.content[:-1] if change == "truncated" else client.content + b"extra"
        client.video_body = io.BytesIO(content)
    with pytest.raises(ValueError):
        restore.restore_wan_output(client, **arguments)
    assert not arguments["destination"].exists()
    assert not list(arguments["destination"].parent.glob("*.partial"))
    assert offline_decode == []


def test_network_disconnect_then_same_identity_recovers_without_submission(arguments, offline_decode):
    client = OfflineS3()

    class DisconnectedBody(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("Offline simulated disconnect")
            return super().read(3)

    client.video_body = DisconnectedBody(client.content)
    with pytest.raises(OSError, match="simulated disconnect"):
        restore.restore_wan_output(client, **arguments)
    assert not arguments["destination"].exists()
    assert not list(arguments["destination"].parent.glob("*.partial"))
    client.video_body = None
    restore.restore_wan_output(client, **arguments)
    assert arguments["destination"].read_bytes() == client.content
    assert len(client.calls) == 4


@pytest.mark.parametrize("failure", ["local_hash", "decode", "decoded_metadata", "remote_hash"])
def test_existing_good_file_is_not_overwritten_on_any_verification_failure(
        arguments, offline_decode, monkeypatch, failure):
    client = OfflineS3()
    path = arguments["destination"]
    path.write_bytes(client.content)
    if failure == "local_hash":
        path.write_bytes(b"X" * len(client.content))
    elif failure == "remote_hash":
        client.report["media"]["final"]["sha256"] = "0" * 64
    elif failure == "decode":
        def reject(*_):
            raise ValueError("Offline simulated decode failure")
        monkeypatch.setattr(restore, "verify_mp4", reject)
    else:
        monkeypatch.setattr(restore, "verify_mp4", lambda *_: {**restore.FINAL_SPEC, "fps": 16})
    previous = path.read_bytes()
    with pytest.raises(ValueError):
        restore.restore_wan_output(client, **arguments)
    assert path.read_bytes() == previous
    assert len(client.calls) == 1


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="Local FFmpeg tools unavailable")
def test_cpu_synthetic_fixture_restores_and_fully_decodes_without_reencoding(arguments, tmp_path):
    # This CPU color fixture proves recovery mechanics, never Wan inference success.
    synthetic = tmp_path / "CPU_SYNTHETIC_NOT_WAN.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=774x1376:r=24", "-frames:v", "120", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(synthetic)],
                   check=True, timeout=60)
    client = OfflineS3(synthetic.read_bytes())
    first = restore.restore_wan_output(client, **arguments)
    second = restore.restore_wan_output(client, **arguments)
    assert first == second
    assert arguments["destination"].read_bytes() == synthetic.read_bytes()
    assert first[2] == {**restore.FINAL_SPEC, "audio_present": False}
