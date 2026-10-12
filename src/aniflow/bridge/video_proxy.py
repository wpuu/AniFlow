"""Single-request Agnes video relay for the existing loopback AniFlow UI.

Browsers cannot rely on the public Agnes CORS wildcard to allow Authorization.
This relay is *not* a new multi-provider backend: it forwards one explicitly
requested Agnes POST, or one read-only Agnes task-status GET. It never retries.
The Bridge must remain bound to the loopback interface.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aniflow.config import Settings

VideoModel = Literal["agnes-video-2.5-flash", "agnes-video-2.5", "agnes-video-v2.0"]


class CreateVideoRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)
    payload: dict[str, Any] = Field(min_length=1, max_length=24)


class VideoStatusRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)
    video_id: str = Field(min_length=1, max_length=256)
    model_name: VideoModel


def _upstream_root(settings: Settings) -> str:
    root = settings.agnes_api_root.rstrip("/")
    root = root.removesuffix("/v1")
    if not root.startswith("https://"):
        raise HTTPException(status_code=500, detail="Agnes API must use HTTPS")
    return root


def _safe_payload(response: httpx.Response, api_key: str) -> JSONResponse:
    if 300 <= response.status_code < 400:
        raise HTTPException(status_code=502, detail="Unexpected Agnes redirect; not followed")
    if len(response.content) > 1024 * 1024:
        raise HTTPException(status_code=502, detail="Unexpectedly large Agnes task response")
    if api_key in response.text:
        raise HTTPException(status_code=502, detail="Upstream response echoed a credential")
    try:
        parsed = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agnes returned non-JSON HTTP {response.status_code}",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Unexpected Agnes response format")
    return JSONResponse(status_code=response.status_code, content=parsed)


def video_proxy_router(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> APIRouter:
    router = APIRouter()

    async def forward(
        method: Literal["GET", "POST"],
        path: str,
        api_key: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> JSONResponse:
        url = _upstream_root(settings) + path
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(45.0, connect=10.0),
                follow_redirects=False,
                transport=transport,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    params=params,
                )
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail="Agnes request timed out; a video POST may have been accepted. Do not retry.",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="Agnes network error; a video POST may have been accepted. Check original task.",
            ) from exc
        return _safe_payload(response, api_key)

    @router.post("/api/video/create")
    async def create_video(request: CreateVideoRequest) -> JSONResponse:
        model = request.payload.get("model")
        if model not in ("agnes-video-2.5-flash", "agnes-video-2.5"):
            # Legacy v2.0 history can be displayed, but new paid requests must
            # never accidentally fall through a legacy permissive path.
            raise HTTPException(status_code=422, detail="Unsupported Agnes video model")
        if not isinstance(request.payload.get("prompt"), str) or not request.payload["prompt"].strip():
            raise HTTPException(status_code=422, detail="Video prompt must be nonempty")
        if model in ("agnes-video-2.5-flash", "agnes-video-2.5"):
            mode = request.payload.get("mode")
            if mode not in ("text", "keyframe", "reference"):
                raise HTTPException(status_code=422, detail="Unsupported Flash video mode")
            if mode == "reference":
                images = request.payload.get("images")
                if (
                    not isinstance(images, list)
                    or not 1 <= len(images) <= 5
                    or any(
                        not isinstance(image, str) or not image.startswith("https://")
                        for image in images
                    )
                    or any(
                        request.payload.get(field)
                        for field in ("first_frame", "last_frame", "videos")
                    )
                ):
                    raise HTTPException(status_code=422, detail="Invalid reference images")
            elif mode == "text":
                if any(
                    request.payload.get(field)
                    for field in ("first_frame", "last_frame", "images", "audios", "videos")
                ):
                    raise HTTPException(status_code=422, detail="Text mode excludes media")
            elif not (request.payload.get("first_frame") or request.payload.get("last_frame")):
                raise HTTPException(status_code=422, detail="Keyframe mode needs a frame")
            permitted_sizes = ("720P",) if model.endswith("-flash") else ("720P", "1080P")
            if request.payload.get("n") != 1 or request.payload.get("size") not in permitted_sizes:
                raise HTTPException(status_code=422, detail="Unsupported model size or output count")
            if str(request.payload.get("seconds")) not in {str(s) for s in range(4, 13)}:
                raise HTTPException(status_code=422, detail="Flash length must be 4–12 seconds")
        return await forward("POST", "/v1/videos", request.api_key, payload=request.payload)

    @router.post("/api/video/status")
    async def video_status(request: VideoStatusRequest) -> JSONResponse:
        return await forward(
            "GET",
            "/agnesapi",
            request.api_key,
            params={"video_id": request.video_id, "model_name": request.model_name},
        )

    return router
