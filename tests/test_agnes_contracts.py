import pytest

from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.video import AgnesVideoClient
from aniflow.config import Settings


class CaptureHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def request_json(self, method, url, *, api_key, json=None, params=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "api_key": api_key,
                "json": json,
                "params": params,
            }
        )
        return self.response


@pytest.mark.asyncio
async def test_image_21_flash_reference_request_uses_official_extra_body_contract():
    settings = Settings()
    http = CaptureHttp(
        {
            "data": [
                {
                    "url": "https://example.com/generated.png",
                    "b64_json": None,
                    "revised_prompt": None,
                }
            ]
        }
    )
    client = AgnesImageClient(settings, http)

    result = await client.generate(
        api_key="secret",
        prompt="preserve the fox identity",
        size="1K",
        ratio="9:16",
        reference_images=["https://example.com/ref1.png", "https://example.com/ref2.png"],
    )

    payload = http.calls[0]["json"]
    assert http.calls[0]["method"] == "POST"
    assert http.calls[0]["url"].endswith("/v1/images/generations")
    assert payload["model"] == "agnes-image-2.1-flash"
    assert payload["size"] == "1K"
    assert payload["ratio"] == "9:16"
    assert payload["extra_body"]["image"] == [
        "https://example.com/ref1.png",
        "https://example.com/ref2.png",
    ]
    assert payload["extra_body"]["response_format"] == "url"
    assert "response_format" not in payload
    assert result.url == "https://example.com/generated.png"


@pytest.mark.asyncio
async def test_video_25_flash_keyframe_request_uses_official_flash_contract():
    settings = Settings(aniflow_video_seconds=5, aniflow_aspect_ratio="9:16")
    http = CaptureHttp({"video_id": "vid-123", "status": "queued"})
    client = AgnesVideoClient(settings, http)

    task = await client.create_keyframe_task(
        api_key="secret",
        prompt="small controlled movement, locked camera",
        first_frame_url="https://example.com/a.png",
        last_frame_url="https://example.com/b.png",
    )

    payload = http.calls[0]["json"]
    assert http.calls[0]["method"] == "POST"
    assert http.calls[0]["url"].endswith("/v1/videos")
    assert payload["model"] == "agnes-video-2.5-flash"
    assert payload["mode"] == "keyframe"
    assert payload["seconds"] == "5"
    assert payload["size"] == "720P"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["n"] == 1
    assert payload["first_frame"] == "https://example.com/a.png"
    assert payload["last_frame"] == "https://example.com/b.png"
    assert task.video_id == "vid-123"


@pytest.mark.asyncio
async def test_video_25_flash_retrieval_always_includes_model_name_for_keyframe_jobs():
    settings = Settings()
    http = CaptureHttp(
        {
            "status": "completed",
            "metadata": {"url": "https://example.com/result.mp4"},
        }
    )
    client = AgnesVideoClient(settings, http)

    result = await client.retrieve(api_key="secret", video_id="vid-123")

    call = http.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/agnesapi")
    assert call["params"] == {
        "video_id": "vid-123",
        "model_name": "agnes-video-2.5-flash",
    }
    assert result.video_url == "https://example.com/result.mp4"
