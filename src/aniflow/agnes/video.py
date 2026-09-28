from __future__ import annotations

import asyncio
import time

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.config import Settings
from aniflow.models import VideoResult, VideoTask


class AgnesVideoClient:
    def __init__(self, settings: Settings, http: AgnesHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def create_keyframe_task(
        self,
        *,
        api_key: str,
        prompt: str,
        first_frame_url: str | None = None,
        last_frame_url: str | None = None,
        seconds: int | None = None,
        aspect_ratio: str | None = None,
        seed: int | None = None,
    ) -> VideoTask:
        if not first_frame_url and not last_frame_url:
            raise ValueError("keyframe mode requires first_frame_url or last_frame_url")

        payload: dict = {
            "model": self.settings.agnes_video_model,
            "prompt": prompt,
            "seconds": str(seconds or self.settings.aniflow_video_seconds),
            "mode": "keyframe",
            "size": "720P",
            "aspect_ratio": aspect_ratio or self.settings.aniflow_aspect_ratio,
            "n": 1,
        }
        if first_frame_url:
            payload["first_frame"] = first_frame_url
        if last_frame_url:
            payload["last_frame"] = last_frame_url
        if seed is not None:
            payload["seed"] = seed

        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/videos",
            api_key=api_key,
            json=payload,
        )
        video_id = data.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            raise AgnesApiError("Agnes video create response did not contain video_id")
        return VideoTask(video_id=video_id, status=data.get("status"), raw=data)

    async def retrieve(self, *, api_key: str, video_id: str) -> VideoResult:
        data = await self.http.request_json(
            "GET",
            f"{self.settings.agnes_api_root.rstrip('/')}/agnesapi",
            api_key=api_key,
            params={"video_id": video_id, "model_name": self.settings.agnes_video_model},
        )
        # Official contract (wiki.agnes-ai.com/en/docs/agnes-video-25-flash):
        # the completed retrieve response exposes the playable address as a
        # TOP-LEVEL `url` field. There is no `metadata` object in the documented
        # payload. Reading `metadata.url` made every completed task look broken.
        # `metadata.url` is kept only as a defensive fallback.
        status = str(data.get("status") or "unknown")
        url = data.get("url")
        if not isinstance(url, str) or not url:
            metadata = data.get("metadata")
            url = metadata.get("url") if isinstance(metadata, dict) else None
        if not isinstance(url, str) or not url:
            url = None
        return VideoResult(video_id=video_id, status=status, video_url=url, raw=data)

    async def wait_for_result(
        self,
        *,
        api_key: str,
        video_id: str,
        poll_seconds: float = 1.5,
        timeout_seconds: float = 900.0,
    ) -> VideoResult:
        started = time.monotonic()
        while True:
            result = await self.retrieve(api_key=api_key, video_id=video_id)
            if result.status == "completed":
                if not result.video_url:
                    raise AgnesApiError("Video completed but no top-level `url` was returned")
                return result
            if result.status == "failed":
                error = result.raw.get("error") or {}
                message = error.get("message") if isinstance(error, dict) else str(error)
                raise AgnesApiError(f"Video generation failed: {message or 'unknown error'}")
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError(f"Timed out waiting for Agnes video {video_id}")
            await asyncio.sleep(poll_seconds)
