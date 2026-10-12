"""No-key contract tests for the existing nine-key UI's localhost video relay."""

from __future__ import annotations

import json

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



def test_flash_reference_mode_forwards_one_image_as_reference_not_keyframe() -> None:
    calls: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"video_id": "video_reference_1", "status": "queued"})

    source = "https://raw.githubusercontent.com/wpuu/AniFlow/4a09aa3d93f25f753c3379fd8bf4501427a266a0/assets/character/agnes-felt-test-frame.png"
    payload = {
        **GOOD_PAYLOAD, "mode": "reference",
        "prompt": "Use <Picture 1> as researcher cat; add water bowl.",
        "images": [source],
    }
    with client_for(respond) as client:
        result = client.post(
            "/api/video/create", json={"api_key": FAKE_KEY, "payload": payload}
        )
    assert result.status_code == 200
    assert result.json()["video_id"] == "video_reference_1"
    assert calls == [payload]
    assert all(field not in calls[0] for field in ("first_frame", "last_frame", "videos"))


def test_invalid_reference_images_are_blocked_before_any_external_post() -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    source = "https://raw.githubusercontent.com/wpuu/AniFlow/4a09aa3d93f25f753c3379fd8bf4501427a266a0/assets/character/agnes-felt-test-frame.png"
    invalid = [
        {**GOOD_PAYLOAD, "mode": "reference"},
        {**GOOD_PAYLOAD, "mode": "reference", "images": []},
        {**GOOD_PAYLOAD, "mode": "reference", "images": [source] * 6},
        {**GOOD_PAYLOAD, "mode": "reference", "images": ["http://localhost/a.png"]},
        {**GOOD_PAYLOAD, "mode": "reference", "images": [source], "first_frame": source},
        {**GOOD_PAYLOAD, "mode": "text", "images": [source]},
    ]
    with client_for(respond) as client:
        for payload in invalid:
            result = client.post(
                "/api/video/create", json={"api_key": FAKE_KEY, "payload": payload}
            )
            assert result.status_code == 422
    assert calls == 0



def test_rebinding_host_is_rejected_before_any_create_or_status_upstream_call() -> None:
    """A localhost TCP listener is not enough: reject a foreign Host."""
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"video_id": "should_never_exist"})

    with client_for(respond) as client:
        for route, data in (
            ("/api/video/create", {"api_key": FAKE_KEY, "payload": GOOD_PAYLOAD}),
            ("/api/video/status", {
                "api_key": FAKE_KEY,
                "video_id": "an_existing_id",
                "model_name": "agnes-video-2.5-flash",
            }),
        ):
            reply = client.post(
                route,
                headers={"Host": "127.0.0.1.attacker.example"},
                json=data,
            )
            assert reply.status_code == 400
    assert calls == []


def test_foreign_browser_origin_cannot_pass_preflight_and_no_video_is_created() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"video_id": "should_never_exist"})

    with client_for(respond) as client:
        reply = client.options(
            "/api/video/create",
            headers={
                "Host": "localhost:8765",
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert reply.status_code == 400
    assert "https://attacker.example" not in reply.headers.get(
        "access-control-allow-origin", ""
    )
    assert calls == []


def test_valid_loopback_host_still_accepts_one_explicit_mocked_create() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"video_id": "mock_existing_one", "status": "queued"})

    with client_for(respond) as client:
        response = client.post(
            "/api/video/create",
            headers={"Host": "127.0.0.1:8765"},
            json={"api_key": FAKE_KEY, "payload": GOOD_PAYLOAD},
        )
    assert response.status_code == 200
    assert response.json()["video_id"] == "mock_existing_one"
    assert len(calls) == 1



def test_paid_agnes_25_accepts_documented_720p_and_1080p_without_autoretry() -> None:
    actual: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        actual.append(json.loads(request.content))
        return httpx.Response(200, json={"video_id": "paid_video_fake_1", "status": "queued"})

    with client_for(respond) as client:
        result = client.post("/api/video/create", json={
            "api_key": FAKE_KEY,
            "payload": {**GOOD_PAYLOAD, "model": "agnes-video-2.5", "size": "1080P"},
        })
    assert result.status_code == 200
    assert len(actual) == 1
    assert actual[0]["model"] == "agnes-video-2.5"
    assert actual[0]["size"] == "1080P"


def test_v2_legacy_creation_and_invalid_paid_resolutions_block_before_post() -> None:
    attempts: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(200, json={})

    with client_for(respond) as client:
        for payload in (
            {**GOOD_PAYLOAD, "model": "agnes-video-v2.0"},
            {**GOOD_PAYLOAD, "model": "agnes-video-2.5", "size": "480P"},
            {**GOOD_PAYLOAD, "model": "agnes-video-2.5", "size": "2K"},
        ):
            result = client.post("/api/video/create", json={
                "api_key": FAKE_KEY, "payload": payload,
            })
            assert result.status_code == 422
    assert not attempts



def test_video_keyframe_accepts_local_base64_data_uri_without_s3() -> None:
    import json

    seen = []
    local_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

    def accept(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"video_id": "mock_keyframe_inline_1", "status": "queued"})

    with client_for(accept) as client:
        result = client.post("/api/video/create", json={
            "api_key": FAKE_KEY, "payload": {
                **GOOD_PAYLOAD, "mode": "keyframe", "first_frame": local_image,
            },
        })
    assert result.status_code == 200
    assert seen[0]["first_frame"] == local_image
    assert "S3" not in result.text


def test_base64_bad_format_rejected_before_provider() -> None:
    called = 0

    def upstream(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called += 1
        return httpx.Response(200, json={})

    with client_for(upstream) as client:
        for image in ("data:text/html;base64,AAAA", "data:image/png;base64,!!notbase64",
                      "data:image/png;base64," + "A" * 5_500_001):
            result = client.post("/api/video/create", json={
                "api_key": FAKE_KEY, "payload": {
                    **GOOD_PAYLOAD, "mode": "keyframe", "first_frame": image,
                },
            })
            assert result.status_code == 422
    assert called == 0
