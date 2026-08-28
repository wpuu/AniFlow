from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from aniflow.agnes.http import AgnesHttpClient
from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.capcut.provider import CapCutSeedreamProvider, SubprocessCapCutRunner
from aniflow.config import Settings, get_settings
from aniflow.image_provider import AgnesImageProvider
from aniflow.media.images import persist_remote_image
from aniflow.media.store import PublicMediaStore

MAX_IMAGE_BYTES = 20 * 1024 * 1024
DEV_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


class HealthResponse(BaseModel):
    ok: bool = True
    media_ready: bool
    capcut_runner_ready: bool
    capcut_ready: bool
    frontend_ready: bool
    capcut_model: str | None = None
    bridge: str = "aniflow-local"


class UploadResponse(BaseModel):
    url: str
    object_key: str
    size_bytes: int


class GenerateImageRequest(BaseModel):
    provider: Literal["agnes", "capcut"]
    prompt: str = Field(min_length=1, max_length=12000)
    references: list[str] = Field(default_factory=list, max_length=8)
    ratio: str = "9:16"
    size: str = "1K"
    api_key: str | None = None
    model: str | None = None


class GenerateImageResponse(BaseModel):
    provider: Literal["agnes", "capcut"]
    model: str
    url: str


def _detect_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return ".webp"
    raise HTTPException(status_code=415, detail="Only PNG, JPEG and WEBP images are supported")


def create_bridge_app(
    *,
    settings: Settings | None = None,
    media_store: PublicMediaStore | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    app = FastAPI(title="AniFlow Local Bridge", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_FRONTEND_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    def resolve_store() -> PublicMediaStore:
        if media_store is not None:
            return media_store
        if not cfg.s3_ready:
            raise HTTPException(
                status_code=503,
                detail="Public media storage is not configured; set the S3/R2 environment variables first",
            )
        return PublicMediaStore(cfg)

    @app.get("/", include_in_schema=False)
    async def frontend_root():
        if cfg.frontend_ready:
            return FileResponse(cfg.frontend_index_path, media_type="text/html")
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "detail": (
                    "AniFlow frontend has not been built. Run npm run build in "
                    "apps/grok-frontend, then refresh this page."
                ),
                "expected_index": str(cfg.frontend_index_path),
            },
        )

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            media_ready=bool(media_store is not None or cfg.s3_ready),
            capcut_runner_ready=cfg.capcut_runner_ready,
            capcut_ready=cfg.capcut_ready,
            frontend_ready=cfg.frontend_ready,
            capcut_model=cfg.capcut_seedream_model or None,
        )

    @app.post("/api/media/upload", response_model=UploadResponse)
    async def upload_media(file: UploadFile = File(...)) -> UploadResponse:
        raw = await file.read(MAX_IMAGE_BYTES + 1)
        if not raw:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds 20 MiB limit")
        suffix = _detect_suffix(raw)
        object_key = f"aniflow/uploads/{uuid4().hex}{suffix}"
        store = resolve_store()

        with tempfile.TemporaryDirectory(prefix="aniflow-bridge-") as tmp:
            local_path = Path(tmp) / f"upload{suffix}"
            local_path.write_bytes(raw)
            url = await store.upload(local_path, object_key)

        return UploadResponse(url=url, object_key=object_key, size_bytes=len(raw))

    @app.post("/api/images/generate", response_model=GenerateImageResponse)
    async def generate_image(request: GenerateImageRequest) -> GenerateImageResponse:
        store = resolve_store()

        if request.provider == "capcut":
            model = (request.model or cfg.capcut_seedream_model).strip()
            if not cfg.capcut_runner_ready or not model:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "CapCut provider needs CAPCUT_RUNNER_COMMAND and a model name. "
                        "The model may be entered directly in the AniFlow page."
                    ),
                )
            runner = SubprocessCapCutRunner(
                cfg.capcut_runner_command,
                timeout_seconds=cfg.capcut_runner_timeout_seconds,
            )
            provider = CapCutSeedreamProvider(runner=runner, media_store=store, model=model)
            try:
                url = await provider.generate(
                    prompt=request.prompt,
                    references=request.references,
                    size=request.size,
                    ratio=request.ratio,
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"CapCut generation failed: {exc}") from exc
            return GenerateImageResponse(provider="capcut", model=model, url=url)

        api_key = (request.api_key or "").strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="Agnes image generation requires api_key")

        http = AgnesHttpClient()
        try:
            provider = AgnesImageProvider(KeyPool([api_key]), AgnesImageClient(cfg, http))
            temporary_url = await provider.generate(
                prompt=request.prompt,
                references=request.references,
                size=request.size,
                ratio=request.ratio,
            )
            public_url = await persist_remote_image(
                media_store=store,
                source_url=temporary_url,
                object_key_without_suffix=f"aniflow/bridge/agnes/{uuid4().hex}",
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Agnes image generation failed: {exc}") from exc
        finally:
            await http.aclose()

        return GenerateImageResponse(
            provider="agnes",
            model=cfg.agnes_image_model,
            url=public_url,
        )

    return app


app = create_bridge_app()
