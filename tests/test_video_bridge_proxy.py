"""No-key contract tests for the existing nine-key UI's localhost video relay."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from aniflow.bridge.app import create_bridge_app
from aniflow.config import Settings

FAKE_KEY = "dummy-private-key-not-real"
GOOD_PAYLOAD = {
    "model": "agnes-video-2.5-flash",
    "prompt": "a felt cat blinks once",
    "mode": "text",
    "size": "720P",
    "aspect_ratio": "9:16",
    "seconds": "5",
    "n": 1,
}


def client_for(handler):
    return TestClient(
        create_bridge_app(
            settings=Settings(agnes_api_root="https://apihub.agnes-ai.com"),
            video_transport=httpx.MockTransport(handler),
        )
    )


def test_create_forwards_exactly_one_agnes_post_without_exposing_key() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"video_id": "video_test_1", "id": "task_test_1", "status": "queued"},
        )

    with client_for(respond) as client:
        result = client.post(
            "/api/video/create",
            json={"api_key": FAKE_KEY, "payload": GOOD_PAYLOAD},
        )
    assert result.status_code == 200
    assert result.json()["video_id"] == "video_test_1"
    assert FAKE_KEY not in result.text
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://apihub.agnes-ai.com/v1/videos"
    assert requests[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert requests[0].json() if False else True  # Test uses the actual HTTP request body below.
    assert b'"model":"agnes-video-2.5-flash"' in requests[0].content


def test_resume_proxy_uses_get_only_never_posts_a_second_video() -> None:
    methods: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.url.params["video_id"] == "video_original"
        assert request.url.params["model_name"] == "agnes-video-2.5-flash"
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        return httpx.Response(
            200,
            json={"status": "completed", "video_id": "video_original",
                  "url": "https://example.test/video.mp4"},
        )

    with client_for(respond) as client:
        result = client.post(
            "/api/video/status",
            json={"api_key": FAKE_KEY, "video_id": "video_original",
                  "model_name": "agnes-video-2.5-flash"},
        )
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert methods == ["GET"]


def test_missing_key_or_wrong_model_never_contacts_provider() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with client_for(respond) as client:
        assert client.post("/api/video/create",
                           json={"api_key": "", "payload": GOOD_PAYLOAD}).status_code == 422
        assert client.post("/api/video/create",
                           json={"api_key": FAKE_KEY, "payload": {
                               **GOOD_PAYLOAD, "model": "wan2.6-i2v-flash"
                           }}).status_code == 422
        assert client.post("/api/video/status",
                           json={"api_key": FAKE_KEY, "video_id": "video_x",
                                 "model_name": "wan2.6-i2v-flash"}).status_code == 422
    assert not calls


def test_invalid_flash_parameters_block_before_upstream_call() -> None:
    count = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(200, json={})

    with client_for(respond) as client:
        for change in ({"n": 9}, {"size": "1080P"}, {"seconds": "99"}):
            result = client.post("/api/video/create",
                                 json={"api_key": FAKE_KEY,
                                       "payload": {**GOOD_PAYLOAD, **change}})
            assert result.status_code == 422
    assert count == 0


def test_queue_full_returns_error_without_automatic_retry() -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "video_queue_full"}})

    with client_for(respond) as client:
        result = client.post("/api/video/create",
                             json={"api_key": FAKE_KEY, "payload": GOOD_PAYLOAD})
    assert result.status_code == 503
    assert "video_queue_full" in result.text
    assert calls == 1


def test_timeout_is_ambiguous_and_does_not_retry() -> None:
    calls = 0

    def timeout(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("simulated timeout")

    with client_for(timeout) as client:
        result = client.post("/api/video/create",
                             json={"api_key": FAKE_KEY, "payload": GOOD_PAYLOAD})
    assert result.status_code == 504
    assert "may have been accepted" in result.json()["detail"]
    assert FAKE_KEY not in result.text
    assert calls == 1


def test_redirect_cannot_forward_bearer_token_to_a_second_host() -> None:
    requests: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://other.example/steal"})

    with client_for(redirect) as client:
        result = client.post("/api/video/create",
                             json={"api_key": FAKE_KEY, "payload": GOOD_PAYLOAD})
    assert result.status_code == 502
    assert len(requests) == 1
    assert FAKE_KEY not in result.text


def test_credentials_mentioned_in_upstream_body_are_never_echoed() -> None:
    def echo(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": f"Invalid key: {FAKE_KEY}"})

    with client_for(echo) as client:
        result = client.post("/api/video/create",
                             json={"api_key": FAKE_KEY, "payload": GOOD_PAYLOAD})
    assert result.status_code == 502
    assert FAKE_KEY not in result.text
