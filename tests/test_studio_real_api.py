"""Offline contract tests only: local synthetic MP4, no real H3, AWS, or model calls."""
import base64
import hashlib
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from aniflow.studio.comfy_provider import ComfyProvider, verify_mp4
from aniflow.studio.real_api import (
    CHECKS,
    GAMELIFT_CHECKS,
    WORKSPACES_CHECKS,
    RealConfig,
    create_real_app,
)

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO/6G7cAAAAASUVORK5CYII=")


class LocalComfyContract:
    def __init__(self):
        self.posts = 0
        self.key = None
        self.lost_response = False
        self.visible = True
        self.done = False
        self.content = b"bad media"
        self.download_fails = False
        self.devices = [{"type": "cuda", "name": "SYNTHETIC GPU FOR CONTRACT ONLY", "vram_total": 48 * 1024**3}]
        self.uploads = 0

    def __call__(self, request):
        path = request.url.path
        if path == "/system_stats":
            return httpx.Response(200, json={"devices": self.devices})
        if path == "/upload/image":
            self.uploads += 1
            return httpx.Response(200, json={"name": "contract.png", "subfolder": ""})
        if path == "/prompt":
            self.posts += 1
            self.key = json.loads(request.content)["extra_data"]["aniflow_request_key"]
            if self.lost_response:
                raise httpx.ReadError("Synthetic accepted response loss")
            return httpx.Response(200, json={"prompt_id": "server-returned-id"})
        prompt = [1, "server-returned-id", {}, {"aniflow_request_key": self.key}]
        if path == "/queue":
            return httpx.Response(200, json={"queue_running": [], "queue_pending":
                [prompt] if self.key and self.visible and not self.done else []})
        if path.startswith("/history"):
            history = {"server-returned-id": {"prompt": prompt,
                "status": {"completed": True, "status_str": "success"}, "outputs": {
                    "9": {"videos": [{"filename": "LOCAL_CONTRACT_NOT_H3.mp4",
                                       "subfolder": "", "type": "output"}]}}}}
            return httpx.Response(200, json=history if self.done else {})
        if path == "/view":
            if self.download_fails:
                raise httpx.ReadError("Synthetic download outage")
            return httpx.Response(200, content=self.content)
        raise AssertionError(f"Unexpected local contract request {request.method} {path}")


def config(tmp_path):
    # Synthetic audit data is restricted to the test directory and MockTransport.
    workflow = tmp_path / "synthetic-workflow.json"
    workflow.write_text(json.dumps({"source_url": "https://github.com/Comfy-Org/ComfyUI/blob/TEST_ONLY/workflow.json",
        "prompt": {"1": {"class_type": "LOCAL_CONTRACT_ONLY", "inputs": {"image": "", "text": ""}}},
        "bindings": {"image": ["1", "image"], "prompt": ["1", "text"]}}), encoding="utf-8")
    gate = tmp_path / "synthetic-gate.json"
    gate.write_text(json.dumps({"launch_allowed": True, "region": "ap-northeast-1",
        "instance_type": "g6e.2xlarge", "checks": dict.fromkeys(CHECKS, True),
        "expires_at_unix": time.time() + 60, "max_runtime_seconds": 60,
        "experiment_budget_usd": 1, "workflow_sha256": hashlib.sha256(workflow.read_bytes()).hexdigest()}),
        encoding="utf-8")
    return RealConfig(tmp_path / "data", gate_path=gate, workflow_path=workflow)


def payload(client, key="contract-request-001"):
    upload = client.post("/api/studio/real/assets", files={"file": ("frame.png", PNG, "image/png")})
    assert upload.status_code == 200
    return {"project_id": "ContractOnly", "shot_id": "One", "image_id": upload.json()["image_id"],
            "prompt": "Synthetic contract, not real H3", "negative_prompt": "", "duration_seconds": 5,
            "aspect_ratio": "9:16", "idempotency_key": key, "provider": "minimax-h3"}


def test_default_real_is_blocked_and_rejects_cross_origin(tmp_path):
    upstream = LocalComfyContract()
    with TestClient(create_real_app(RealConfig(tmp_path), httpx.MockTransport(upstream))) as client:
        health = client.get("/api/studio/real/health").json()
        assert health["mode"] == "REAL_H3" and health["simulation"] is False
        assert health["ready"] is False and health["blocked_reasons"]
        p = payload(client)
        assert client.post("/api/studio/real/jobs", json=p).status_code == 403
        assert client.post("/api/studio/real/jobs", json=p,
                           headers={"Origin": "https://unrelated.example"}).status_code == 403
        assert client.post("/api/studio/mock/jobs", json=p).status_code == 404
        assert client.get("/api/studio/real/jobs").json()["jobs"] == []
        assert upstream.posts == 0


def workspaces_config(tmp_path):
    cfg = config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate.update(service="workspaces", instance_type="Graphics.g6.4xlarge",
                cash_cap_usd=1, credit_budget_usd=20,
                checks=dict.fromkeys(WORKSPACES_CHECKS, True))
    del gate["experiment_budget_usd"]
    cfg.gate_path.write_text(json.dumps(gate))
    add_postprocess(cfg, {"preset": "h3_native_5s_portrait_v1"})
    return cfg


@pytest.mark.parametrize("cash_cap", [0, 1])
def test_workspaces_gate_has_separate_credit_and_cash_budgets(tmp_path, cash_cap):
    upstream, cfg = LocalComfyContract(), workspaces_config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate["cash_cap_usd"] = cash_cap
    cfg.gate_path.write_text(json.dumps(gate))
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        assert client.get("/api/studio/real/health").json()["ready"] is True
        assert client.post("/api/studio/real/jobs", json=payload(client)).status_code == 202
        assert upstream.posts == 1


@pytest.mark.parametrize(("field", "value"), [
    ("service", "unknown"), ("service", "ec2"), ("instance_type", "g6e.2xlarge"),
    ("region", "us-east-1"), ("cash_cap_usd", 1.01), ("cash_cap_usd", -1),
    ("cash_cap_usd", None), ("credit_budget_usd", 20.01),
    ("credit_budget_usd", 0), ("credit_budget_usd", None),
    ("max_runtime_seconds", 14401), ("launch_allowed", False)])
def test_workspaces_gate_rejects_resource_and_budget_mismatch(tmp_path, field, value):
    upstream, cfg = LocalComfyContract(), workspaces_config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate[field] = value
    cfg.gate_path.write_text(json.dumps(gate))
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        assert client.get("/api/studio/real/health").json()["ready"] is False
        assert client.post("/api/studio/real/jobs", json=payload(client)).status_code == 403
        assert upstream.posts == 0 and upstream.uploads == 0


@pytest.mark.parametrize("check", WORKSPACES_CHECKS)
def test_workspaces_gate_requires_each_service_specific_audit_check(tmp_path, check):
    cfg = workspaces_config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    # EC2 eligibility cannot substitute for WorkSpaces credit/quota/account audits.
    gate["checks"].update(dict.fromkeys(CHECKS, True))
    gate["checks"].pop(check)
    cfg.gate_path.write_text(json.dumps(gate))
    assert cfg.audited_workflow()[0]


def test_real_preflight_without_audit_is_unknown_not_mock(tmp_path):
    upstream = LocalComfyContract()
    with TestClient(create_real_app(RealConfig(tmp_path), httpx.MockTransport(upstream))) as client:
        data = client.get("/api/studio/cloud/preflight").json()
        assert data["mode"] == "LOCAL_AUDIT_PROJECTION" and data["service"] == "workspaces"
        assert data["instance_type"] == "Graphics.g6.4xlarge" and data["region"] == "ap-northeast-1"
        assert data["expected_gpu"] == "NVIDIA L4" and data["expected_gpu_vram_gib"] == 24
        assert data["expected_ram_gib"] == 64 and data["account_plan"] == "unknown"
        assert data["checks"] == dict.fromkeys(WORKSPACES_CHECKS)
        assert data["launch_allowed"] is False and data["blocked_reasons"]
        assert data["real_gpu_connected"] is True and data["tunnel_connected"] is True
        assert data["estimated_credit_remaining_usd"] is None and data["hourly_price_usd"] is None
        assert data["credit_settled_remaining_usd"] is None and data["credit_observed_at_utc"] is None
        assert data["aws_queries"] == 0 and data["aws_writes"] == 0
        assert upstream.posts == 0 and upstream.uploads == 0


@pytest.mark.parametrize("expired", [False, True])
def test_real_preflight_projects_only_valid_workspaces_audit(tmp_path, expired):
    upstream, cfg = LocalComfyContract(), workspaces_config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate.update(account_plan="SYNTHETIC_TEST_PLAN", estimated_credit_remaining_usd=50,
                credit_settled_remaining_usd=55, credit_observed_at_utc="2026-10-26T00:00:00Z",
                hourly_price_usd=2.5)
    if expired:
        gate["expires_at_unix"] = time.time() - 1
    cfg.gate_path.write_text(json.dumps(gate))
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        data = client.get("/api/studio/cloud/preflight").json()
        assert data["launch_allowed"] is not expired
        assert data["checks"] == dict.fromkeys(WORKSPACES_CHECKS, None if expired else True)
        assert data["account_plan"] == ("unknown" if expired else "SYNTHETIC_TEST_PLAN")
        for field in ("estimated_credit_remaining_usd", "credit_settled_remaining_usd",
                      "credit_observed_at_utc", "hourly_price_usd"):
            assert data[field] == (None if expired else gate[field])
        assert upstream.posts == 0 and upstream.uploads == 0


def test_real_preflight_does_not_treat_valid_audit_as_observed_gpu(tmp_path):
    upstream, cfg = LocalComfyContract(), workspaces_config(tmp_path)
    upstream.devices = [{"type": "cpu", "vram_total": 64 * 1024**3}]
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        data = client.get("/api/studio/cloud/preflight").json()
        assert data["checks"] == dict.fromkeys(WORKSPACES_CHECKS, True)
        assert data["launch_allowed"] is False and data["real_gpu_connected"] is False
        assert data["tunnel_connected"] is True and data["blocked_reasons"]


def test_real_preflight_preserves_ec2_gate_service_identity(tmp_path):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        data = client.get("/api/studio/cloud/preflight").json()
        assert data["service"] == "ec2" and data["instance_type"] == "g6e.2xlarge"
        assert data["checks"] == dict.fromkeys(CHECKS, True)
        assert "credit_workspaces_eligible" not in data["checks"]
        assert data["launch_allowed"] is True


def test_workspaces_gate_cannot_omit_strict_postprocess(tmp_path):
    cfg = workspaces_config(tmp_path)
    bundle = json.loads(cfg.workflow_path.read_text())
    del bundle["postprocess"]
    cfg.workflow_path.write_text(json.dumps(bundle))
    gate = json.loads(cfg.gate_path.read_text())
    gate["workflow_sha256"] = hashlib.sha256(cfg.workflow_path.read_bytes()).hexdigest()
    cfg.gate_path.write_text(json.dumps(gate))
    assert cfg.audited_workflow()[0]


def test_lost_submit_response_recovers_without_post_across_restart(tmp_path):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    upstream.lost_response, upstream.visible = True, False
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        p = payload(client)
        first = client.post("/api/studio/real/jobs", json=p).json()
        assert first["status"] == "submission_unknown" and first["comfy_prompt_id"] is None
        assert client.get("/api/studio/real/requests/contract-request-001").json()["status"] == "submission_unknown"
        assert client.post("/api/studio/real/jobs", json=p).json()["id"] == first["id"]
        assert client.post("/api/studio/real/jobs", json={**p, "prompt": "different"}).status_code == 409
        assert client.post("/api/studio/real/jobs", json={**p, "idempotency_key": "second-request"}).status_code == 409
    upstream.visible = True
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        recovered = client.get("/api/studio/real/requests/contract-request-001").json()
        assert recovered["id"] == first["id"]
        assert recovered["comfy_prompt_id"] == "server-returned-id"
        assert recovered["status"] == "queued"
        assert upstream.posts == 1


@pytest.mark.parametrize("devices", [[], [{"type": "cpu", "name": "CPU", "vram_total": 64 * 1024**3}],
                                      [{"type": "cuda", "name": "unknown", "vram_total": 0}]])
def test_cpu_only_tunnel_cannot_report_gpu_or_submit(tmp_path, devices):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    upstream.devices = devices
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        health = client.get("/api/studio/real/health").json()
        assert health["tunnel_connected"] is True
        assert health["gpu_connected"] is False and health["ready"] is False
        assert client.post("/api/studio/real/jobs", json=payload(client)).status_code == 403
        assert upstream.posts == 0 and upstream.uploads == 0
        assert client.get("/api/studio/real/jobs").json()["jobs"] == []


def test_gpu_truth_requires_device_evidence_and_audit_independently(tmp_path):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        health = client.get("/api/studio/real/health").json()
        assert health["tunnel_connected"] is True and health["gpu_connected"] is True
        assert health["ready"] is True
        created = client.post("/api/studio/real/jobs", json=payload(client)).json()
        assert created["gpu_connected"] is True
    with TestClient(create_real_app(RealConfig(tmp_path / "disabled"), httpx.MockTransport(upstream))) as client:
        health = client.get("/api/studio/real/health").json()
        assert health["gpu_connected"] is True and health["ready"] is False


def test_expired_or_modified_workflow_audit_cannot_submit(tmp_path):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate["expires_at_unix"] = time.time() - 1
    cfg.gate_path.write_text(json.dumps(gate))
    assert cfg.audited_workflow()[0]
    gate["expires_at_unix"] = time.time() + 60
    cfg.gate_path.write_text(json.dumps(gate))
    cfg.workflow_path.write_text(cfg.workflow_path.read_text() + " ")
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        assert client.post("/api/studio/real/jobs", json=payload(client)).status_code == 403
        assert upstream.posts == 0


def test_concurrent_same_request_submits_only_once(tmp_path):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        p = payload(client)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post("/api/studio/real/jobs", json=p), range(2)))
        assert all(response.status_code == 202 for response in responses)
        assert len({response.json()["id"] for response in responses}) == 1
        assert upstream.posts == 1


def test_complete_download_is_verified_and_corruption_is_not_served(tmp_path):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    fixture = tmp_path / "LOCAL_CONTRACT_NOT_H3.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=768x1360:r=1:d=5", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", str(fixture)], check=True, timeout=60)
    upstream.content = fixture.read_bytes()
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        first = client.post("/api/studio/real/jobs", json=payload(client)).json()
        upstream.done, upstream.download_fails = True, True
        interrupted = client.get(f"/api/studio/real/jobs/{first['id']}").json()
        assert interrupted["verified"] is False and interrupted["local_path"] is None
        upstream.download_fails = False
        done = client.get(f"/api/studio/real/jobs/{first['id']}").json()
        assert done["status"] == "completed" and done["verified"] is True
        assert done["output_sha256"] == hashlib.sha256(upstream.content).hexdigest()
        assert done["output_bytes"] == len(upstream.content)
        assert done["video_metadata"]["duration_seconds"] == 5
        assert done["actual_cost_usd"] is None and done["peak_vram_mb"] is None
        assert Path(done["local_path"]).read_bytes() == upstream.content
        assert not list(cfg.data_dir.rglob("*.partial"))
        assert client.get(done["video_download_path"]).content == upstream.content
        Path(done["local_path"]).write_bytes(b"corrupt")
        assert client.get(done["video_download_path"]).status_code == 409
        assert upstream.posts == 1


def add_postprocess(cfg, postprocess):
    bundle = json.loads(cfg.workflow_path.read_text())
    bundle["postprocess"] = postprocess
    cfg.workflow_path.write_text(json.dumps(bundle))
    gate = json.loads(cfg.gate_path.read_text())
    gate["workflow_sha256"] = hashlib.sha256(cfg.workflow_path.read_bytes()).hexdigest()
    cfg.gate_path.write_text(json.dumps(gate))


@pytest.fixture(scope="module", params=[True, False], ids=["with-audio", "without-audio"])
def native_contract_video(tmp_path_factory, request):
    fixture = tmp_path_factory.mktemp("synthetic-native") / "LOCAL_CONTRACT_NOT_H3.mp4"
    audio = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"] if request.param else []
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=800x1376:r=24",
                    *audio, "-frames:v", "124", "-t", "5.166666667",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(fixture)], check=True, timeout=60)
    return fixture


def test_native_postprocess_preserves_source_and_verifies_final_after_download_recovery(tmp_path,
                                                                                       native_contract_video):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    add_postprocess(cfg, {"preset": "h3_native_5s_portrait_v1"})
    upstream.content = native_contract_video.read_bytes()
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        first = client.post("/api/studio/real/jobs", json=payload(client)).json()
        upstream.done, upstream.download_fails = True, True
        interrupted = client.get(f"/api/studio/real/jobs/{first['id']}").json()
        assert interrupted["verified"] is False and interrupted["local_path"] is None
        upstream.download_fails = False
        done = client.get(f"/api/studio/real/jobs/{first['id']}").json()
        assert done["status"] == "completed" and done["verified"] is True
        assert Path(done["source_local_path"]).read_bytes() == upstream.content
        assert done["source_sha256"] == hashlib.sha256(upstream.content).hexdigest()
        assert done["source_bytes"] == len(upstream.content)
        assert done["source_video_metadata"]["frame_count"] == 124
        assert done["source_video_metadata"]["width"] == 800
        assert done["source_video_metadata"]["fps"] == 24
        assert done["video_metadata"] == {"duration_seconds": 5, "width": 774, "height": 1376,
            "fps": 24, "frame_count": 120, "sample_aspect_ratio": "1:1",
            "audio_present": done["source_video_metadata"]["audio_present"]}
        final = Path(done["local_path"])
        assert done["output_sha256"] == hashlib.sha256(final.read_bytes()).hexdigest()
        assert done["output_bytes"] == final.stat().st_size
        assert done["output_sha256"] != done["source_sha256"]
        assert client.get(done["video_download_path"]).content == final.read_bytes()
        assert not list(cfg.data_dir.rglob("*.partial"))
        assert upstream.posts == 1


@pytest.mark.parametrize("preset", [None, {}, {"preset": "unknown"},
                                    {"preset": "h3_native_5s_portrait_v1", "width": 1}])
def test_unknown_postprocess_rejects_before_upstream_submission(tmp_path, preset):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    add_postprocess(cfg, preset)
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        assert client.get("/api/studio/real/health").json()["ready"] is False
        assert client.post("/api/studio/real/jobs", json=payload(client)).status_code == 403
        assert upstream.posts == 0 and upstream.uploads == 0


def test_failed_postprocess_keeps_source_evidence_without_completing(tmp_path, native_contract_video,
                                                                    monkeypatch):
    def fail_postprocess(source, path):
        raise ValueError("Synthetic local postprocess failure")

    monkeypatch.setattr("aniflow.studio.real_api.postprocess_h3_portrait", fail_postprocess)
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    add_postprocess(cfg, {"preset": "h3_native_5s_portrait_v1"})
    upstream.content = native_contract_video.read_bytes()
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        first = client.post("/api/studio/real/jobs", json=payload(client)).json()
        upstream.done = True
        failed = client.get(f"/api/studio/real/jobs/{first['id']}").json()
        assert failed["status"] == "failed" and failed["verified"] is False
        assert Path(failed["source_local_path"]).read_bytes() == upstream.content
        assert failed["source_sha256"] == hashlib.sha256(upstream.content).hexdigest()
        assert failed["local_path"] is None and failed["output_sha256"] is None
        assert client.get(f"/api/studio/real/jobs/{first['id']}/video").status_code == 409
        assert upstream.posts == 1


@pytest.mark.parametrize(("dimensions", "fps", "frames"), [
    ("768x1360", 24, 124), ("800x1376", 25, 124), ("800x1376", 24, 123)])
def test_native_source_rejects_wrong_canvas_fps_or_short_frames(tmp_path, dimensions, fps, frames):
    fixture = tmp_path / "INVALID_NATIVE_CONTRACT_NOT_H3.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c=blue:s={dimensions}:r={fps}", "-frames:v", str(frames),
                    "-c:v", "libx264", "-preset", "ultrafast", str(fixture)], check=True, timeout=60)
    with pytest.raises(ValueError):
        verify_mp4(fixture, "h3_native_source")


def test_bad_output_never_completes(tmp_path):
    upstream, cfg = LocalComfyContract(), config(tmp_path)
    with TestClient(create_real_app(cfg, httpx.MockTransport(upstream))) as client:
        first = client.post("/api/studio/real/jobs", json=payload(client)).json()
        upstream.done = True
        done = client.get(f"/api/studio/real/jobs/{first['id']}").json()
        assert done["status"] == "failed" and done["verified"] is False
        assert done["local_path"] is None and done["output_sha256"] is None
        assert not list(cfg.data_dir.rglob("*.partial"))
        assert client.get(f"/api/studio/real/jobs/{first['id']}/video").status_code == 409


@pytest.mark.parametrize("url", ["https://127.0.0.1:8188", "http://remote.example:8188",
                                "http://user:secret@localhost:8188", "http://localhost:8188/path"])
def test_remote_comfy_urls_are_forbidden(url):
    with pytest.raises(ValueError):
        ComfyProvider(url)


def test_blocked_gamelift_snapshot_cannot_borrow_an_unrelated_loopback_gpu(tmp_path):
    snapshot = tmp_path / "blocked.json"
    snapshot.write_text(json.dumps({"service": "gameliftstreams", "region": "ap-northeast-1",
        "instance_type": "gen6n_pro", "snapshot_only": True, "launch_allowed": False,
        "account_plan": "PAID / ACTIVE", "estimated_credit_remaining_usd": 47.25,
        "checks": {name: False for name in GAMELIFT_CHECKS}}))
    cfg = RealConfig(tmp_path / "local", gate_path=snapshot)
    local = LocalComfyContract()
    with TestClient(create_real_app(cfg, httpx.MockTransport(local))) as client:
        health = client.get("/api/studio/real/health").json()
        projection = client.get("/api/studio/cloud/preflight").json()
    assert health["ready"] is False and health["gpu_connected"] is False
    assert projection["service"] == "gameliftstreams"
    assert projection["instance_type"] == "gen6n_pro"
    assert projection["checks"]["tokyo_gamelift_quota"] is False
    assert projection["launch_allowed"] is False and projection["aws_queries"] == 0
    assert projection["real_gpu_connected"] is False


def test_snapshot_only_never_authorizes_launch_even_with_other_valid_fields(tmp_path):
    cfg = config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate["snapshot_only"] = True
    cfg.gate_path.write_text(json.dumps(gate))
    reasons, workflow = cfg.audited_workflow()
    assert reasons and workflow is None


def test_gr6_requires_full_audit_and_projects_its_actual_target_ram(tmp_path):
    cfg = workspaces_config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate["instance_type"] = "Graphics.gr6.4xlarge"
    cfg.gate_path.write_text(json.dumps(gate))
    with TestClient(create_real_app(cfg, httpx.MockTransport(LocalComfyContract()))) as client:
        projection = client.get("/api/studio/cloud/preflight").json()
    assert projection["instance_type"] == "Graphics.gr6.4xlarge"
    assert projection["expected_ram_gib"] == 128


def test_blocked_gr6_snapshot_never_borrows_an_unrelated_local_gpu(tmp_path):
    cfg = workspaces_config(tmp_path)
    gate = json.loads(cfg.gate_path.read_text())
    gate.update(instance_type="Graphics.gr6.4xlarge", snapshot_only=True, launch_allowed=False)
    gate["checks"]["workspaces_account_eligible"] = None
    cfg.gate_path.write_text(json.dumps(gate))
    with TestClient(create_real_app(cfg, httpx.MockTransport(LocalComfyContract()))) as client:
        projection = client.get("/api/studio/cloud/preflight").json()
        health = client.get("/api/studio/real/health").json()
    assert projection["instance_type"] == "Graphics.gr6.4xlarge"
    assert projection["expected_ram_gib"] == 128
    assert projection["checks"]["workspaces_account_eligible"] is None
    assert not projection["launch_allowed"] and not projection["real_gpu_connected"]
    assert not health["ready"] and not health["gpu_connected"]
