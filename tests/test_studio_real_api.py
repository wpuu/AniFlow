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

from aniflow.studio.comfy_provider import ComfyProvider
from aniflow.studio.real_api import CHECKS, RealConfig, create_real_app

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
