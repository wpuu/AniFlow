from __future__ import annotations

import asyncio
import json

from aniflow.agnes.http import AgnesHttpClient
from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.video import AgnesVideoClient
from aniflow.config import Settings


async def main() -> None:
    settings = Settings()
    if not settings.api_keys:
        raise RuntimeError("AGNES_API_KEYS is empty")

    # Smoke test intentionally uses only the first configured account.
    api_key = settings.api_keys[0]
    http = AgnesHttpClient()
    report: dict[str, object] = {
        "account": "account-1",
        "text_model": settings.agnes_text_model,
        "image_model": settings.agnes_image_model,
        "video_model": settings.agnes_video_model,
    }

    try:
        text = await http.request_json(
            "POST",
            f"{settings.agnes_v1_url}/chat/completions",
            api_key=api_key,
            json={
                "model": settings.agnes_text_model,
                "messages": [
                    {
                        "role": "user",
                        "content": "Reply with exactly: ANIFLOW_TEXT_OK",
                    }
                ],
                "temperature": 0,
                "max_tokens": 32,
            },
        )
        text_content = str(text["choices"][0]["message"]["content"]).strip()
        report["text_ok"] = "ANIFLOW_TEXT_OK" in text_content
        report["text_response"] = text_content[:200]

        image_client = AgnesImageClient(settings, http)
        image = await image_client.generate(
            api_key=api_key,
            prompt=(
                "A single tiny orange fox made as a simple handcrafted miniature character, "
                "neutral studio background, full body, no text, vertical composition"
            ),
            size="1K",
            ratio="9:16",
        )
        if not image.url:
            raise RuntimeError("Image smoke test returned no public URL")
        report["image_ok"] = True
        report["image_url"] = image.url

        vision = await http.request_json(
            "POST",
            f"{settings.agnes_v1_url}/chat/completions",
            api_key=api_key,
            json={
                "model": settings.agnes_text_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Inspect this image. Return only JSON with keys "
                                    "image_readable (boolean) and subject (short string)."
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": image.url}},
                        ],
                    }
                ],
                "temperature": 0,
                "max_tokens": 120,
            },
        )
        vision_content = str(vision["choices"][0]["message"]["content"]).strip()
        report["vision_ok"] = bool(vision_content)
        report["vision_response"] = vision_content[:400]

        video_create = await http.request_json(
            "POST",
            f"{settings.agnes_v1_url}/videos",
            api_key=api_key,
            json={
                "model": settings.agnes_video_model,
                "prompt": (
                    "A tiny handcrafted orange fox slowly turns its head and blinks once, "
                    "fixed camera, simple miniature studio, stable anatomy, no text"
                ),
                "seconds": "4",
                "mode": "text",
                "size": "720P",
                "aspect_ratio": "9:16",
                "n": 1,
            },
        )
        video_id = video_create.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            raise RuntimeError("Video smoke test returned no video_id")

        video_client = AgnesVideoClient(settings, http)
        video = await video_client.wait_for_result(
            api_key=api_key,
            video_id=video_id,
            timeout_seconds=900,
        )
        report["video_ok"] = True
        report["video_id"] = video_id
        report["video_url"] = video.video_url
        report["ok"] = bool(
            report.get("text_ok")
            and report.get("image_ok")
            and report.get("vision_ok")
            and report.get("video_ok")
        )
    except Exception as exc:
        report["ok"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise
    finally:
        await http.aclose()

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
