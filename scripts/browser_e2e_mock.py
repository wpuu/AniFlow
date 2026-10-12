"""NO-CREDENTIAL mock of Agnes for browser click-through testing.

Imported only by the CI browser test subprocess; nothing reaches Agnes. All API
requests are intercepted by httpx.MockTransport and the fake MP4 is local.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx
from fastapi.responses import FileResponse, JSONResponse

from aniflow.bridge.app import create_bridge_app
from aniflow.config import Settings

FAKE_VALID_KEY = "E2E_MOCK_VALID_KEY_NOT_A_REAL_SECRET"
FAKE_TIMEOUT_KEY = "E2E_MOCK_TIMEOUT_KEY_NOT_A_REAL_SECRET"
FAKE_QUEUE_FULL_KEY = "E2E_MOCK_QUEUE_FULL_NOT_A_REAL_SECRET"
FAKE_BUSINESS_QUEUE_KEY = "E2E_MOCK_BUSINESS_QUEUE_KEY"
FAKE_CHINA_KEY = "E2E_MOCK_CHINA_KEY"
FAKE_SLOW_KEY = "E2E_MOCK_SLOW_KEY"
STATE: dict[str, object] = {
    "create_calls": 0,
    "status_calls": 0,
    "batch_create_calls": 0,
    "batch_video_ids": [],
    "last_payload": None,
    "has_seen_timeout": False,
    "slow_create_calls": 0,
}


def fake_agnes_provider(request: httpx.Request) -> httpx.Response:
    """The only upstream transport this isolated server ever uses."""
    if request.method == "POST" and request.url.path == "/v1/videos":
        STATE["create_calls"] = int(STATE["create_calls"]) + 1
        if request.headers.get("Authorization") == f"Bearer {FAKE_TIMEOUT_KEY}":
            if not STATE["has_seen_timeout"]:
                STATE["has_seen_timeout"] = True
                raise httpx.ReadTimeout("mock ambiguous submit (zero real network)")
            # On a later EXPLICIT owner click, pretend Agnes returns a video_id.
            return httpx.Response(200, json={"video_id": "e2e_local_mock_video_1", "status": "queued"})
        authorization = request.headers.get("Authorization", "")
        if authorization == f"Bearer {FAKE_QUEUE_FULL_KEY}":
            return httpx.Response(503, json={"error": {"message": "video_queue_full"}})
        if authorization == f"Bearer {FAKE_BUSINESS_QUEUE_KEY}":
            return httpx.Response(200, json={"code": "video_queue_full", "message": "video queue is full", "data": None})
        if authorization == f"Bearer {FAKE_CHINA_KEY}" and request.url.host != "api.agnes-ai.cn":
            return httpx.Response(401, json={"error": {"message": "domain mismatch"}})
        if authorization == f"Bearer {FAKE_SLOW_KEY}":
            STATE["slow_create_calls"] = int(STATE["slow_create_calls"]) + 1
            return httpx.Response(200, json={"video_id": "e2e_local_mock_slow_key", "status": "queued"})
        slot = re.fullmatch(r"Bearer E2E_MOCK_SLOT_KEY_([1-9])", authorization)
        if authorization not in (f"Bearer {FAKE_VALID_KEY}", f"Bearer {FAKE_CHINA_KEY}") and not slot:
            return httpx.Response(401, json={"error": {"message": "fake key was incorrect"}})
        payload = json.loads(request.content)
        STATE["last_payload"] = payload
        if payload.get("model") != "agnes-video-2.5-flash":
            return httpx.Response(400, json={"error": {"message": "wrong mock model"}})
        if slot:
            fake_id = "e2e_local_mock_batch_" + slot.group(1)
            STATE["batch_create_calls"] = int(STATE["batch_create_calls"]) + 1
            STATE["batch_video_ids"].append(fake_id)
        else:
            fake_id = "e2e_local_mock_video_1"
        return httpx.Response(200, json={"video_id": fake_id, "status": "queued"})
    if request.method == "GET" and request.url.path == "/agnesapi":
        STATE["status_calls"] = int(STATE["status_calls"]) + 1
        video_id = request.url.params.get("video_id", "")
        if video_id == "e2e_local_mock_slow_key":
            return httpx.Response(200, json={"video_id": video_id, "status": "in_progress", "progress": 42})
        if video_id != "e2e_local_mock_video_1" and not re.fullmatch(
            r"e2e_local_mock_batch_[1-9]", video_id
        ):
            return httpx.Response(404, json={"error": {"message": "unknown mock video"}})
        return httpx.Response(
            200,
            json={
                "video_id": video_id,
                "status": "completed",
                "url": "http://127.0.0.1:8765/__e2e_fake_video.mp4",
                "seconds": "5",
                "size": "720x1280",
                "progress": 100,
            },
        )
    raise AssertionError("Unexpected Agnes path: this transport never uses the real network")


app = create_bridge_app(
    settings=Settings(
        agnes_api_root="https://not-used-e2e.invalid",
        aniflow_frontend_index="apps/grok-frontend/dist/index.html",
    ),
    video_transport=httpx.MockTransport(fake_agnes_provider),
)


@app.get("/__e2e_state", include_in_schema=False)
async def e2e_state() -> JSONResponse:
    # Credentials are NEVER included in this status endpoint or screenshot.
    return JSONResponse(STATE)


@app.get("/__e2e_fake_video.mp4", include_in_schema=False)
async def e2e_fake_video() -> FileResponse:
    video = Path(os.environ["ANIFLOW_E2E_FAKE_VIDEO_FILE"])
    return FileResponse(video, media_type="video/mp4")


if __name__ == "__main__":
    raise SystemExit("Use: python -m uvicorn scripts.browser_e2e_mock:app")
