"""Offline end-to-end invariants for mock-only local image-to-video work.

Never calls ComfyUI, AWS, Agnes, public networks, or paid models.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from aniflow.studio.mock_api import create_mock_app

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/MOCK_BLUE_LOCAL_NO_AGNES.mp4"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO/6G7cAAAAASUVORK5CYII="
)

def payload(image_id: str, key: str = "test-owner-click-001") -> dict:
    return {
        "project_id": "SnowDirector",
        "shot_id": "MYCL001-01",
        "image_id": image_id,
        "prompt": "Needle-felted tabby cat blinks slowly",
        "negative_prompt": "photorealistic live cat",
        "aspect_ratio": "9:16",
        "duration_seconds": 5,
        "idempotency_key": key,
        "provider": "mock-h3",
    }

def test_upload_create_resume_and_download_are_local_durable(tmp_path: Path) -> None:
    time = [1000.0]
    app = create_mock_app(tmp_path, FIXTURE, clock=lambda: time[0])
    with TestClient(app) as client:
        health = client.get("/api/studio/mock/health").json()
        assert health["mode"] == "MOCK_ONLY"
        assert health["aws_state"] == "NOT_CONNECTED"
        assert health["paid_request_count"] == 0
        img = client.post("/api/studio/mock/assets", files={"file": ("snow.png", ONE_PIXEL_PNG, "image/png")})
        assert img.status_code == 200
        image_id = img.json()["image_id"]
        first = client.post("/api/studio/mock/jobs", json=payload(image_id))
        assert first.status_code == 202
        job_id = first.json()["id"]
        assert job_id.startswith("mock-")
        assert first.json()["status"] == "queued"
        assert first.json()["simulation"] is True
        assert first.json()["actual_cost_usd"] == 0
        assert client.get(f"/api/studio/mock/jobs/{job_id}/video").status_code == 409
        time[0] += 2
        progress = client.get(f"/api/studio/mock/jobs/{job_id}").json()
        assert progress["status"] == "running"
        assert progress["video_download_path"] is None
        time[0] += 7
        done = client.get(f"/api/studio/mock/jobs/{job_id}").json()
        assert done["status"] == "completed"
        assert done["progress"] == 100
        assert done["simulation"] is True
        assert done["output_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        video = client.get(done["video_download_path"])
        assert video.status_code == 200
        assert video.content == FIXTURE.read_bytes()
        assert video.headers["X-AniFlow-Simulation"] == "true"
        again = client.post("/api/studio/mock/jobs", json=payload(image_id))
        assert again.status_code == 202
        assert again.json()["id"] == job_id
        assert len(client.get("/api/studio/mock/jobs").json()["jobs"]) == 1

    # A new app instance is a simulated Bridge restart. Original task survives.
    app2 = create_mock_app(tmp_path, FIXTURE, clock=lambda: time[0])
    with TestClient(app2) as client:
        restored = client.get(f"/api/studio/mock/jobs/{job_id}").json()
        assert restored["status"] == "completed"
        assert restored["id"] == job_id

def test_rejects_unsafe_inputs_and_idempotency_collision(tmp_path: Path) -> None:
    app = create_mock_app(tmp_path, FIXTURE, clock=lambda: 0.0)
    with TestClient(app) as client:
        assert client.post("/api/studio/mock/assets", files={"file": ("invalid.jpg", b"not-an-image", "image/jpeg")}).status_code in (413,415)
        img = client.post("/api/studio/mock/assets", files={"file": ("snow.png", ONE_PIXEL_PNG, "image/png")}).json()
        p = payload(img["image_id"])
        assert client.post("/api/studio/mock/jobs", json=p).status_code == 202
        changed = {**p, "prompt": "completely different motion"}
        assert client.post("/api/studio/mock/jobs", json=changed).status_code == 409
        assert client.post("/api/studio/mock/jobs", json={**p, "idempotency_key": "other-key-001", "provider":"minimax-h3-aws"}).status_code == 422
        assert client.post("/api/studio/mock/jobs", json={**p, "idempotency_key": "third-key-001", "project_id":"../evil"}).status_code == 422
        assert client.get("/api/studio/mock/jobs/unknown").status_code == 404
        assert client.get("/api/studio/mock/jobs?limit=1000").status_code == 422
