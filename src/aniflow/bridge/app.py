from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aniflow.config import Settings, get_settings
from aniflow.media.store import PublicMediaStore

MAX_IMAGE_BYTES = 20 * 1024 * 1024


class HealthResponse(BaseModel):
    ok: bool = True
    media_ready: bool
    bridge: str = "aniflow-local"


class UploadResponse(BaseModel):
    url: str
    object_key: str
    size_bytes: int


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
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(media_ready=cfg.s3_ready)

    @app.post("/api/media/upload", response_model=UploadResponse)
    async def upload_media(file: UploadFile = File(...)) -> UploadResponse:
        if not cfg.s3_ready and media_store is None:
            raise HTTPException(
                status_code=503,
                detail="Public media storage is not configured; set the S3/R2 environment variables first",
            )

        raw = await file.read(MAX_IMAGE_BYTES + 1)
        if not raw:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds 20 MiB limit")
        suffix = _detect_suffix(raw)
        object_key = f"aniflow/uploads/{uuid4().hex}{suffix}"
        store = media_store or PublicMediaStore(cfg)

        with tempfile.TemporaryDirectory(prefix="aniflow-bridge-") as tmp:
            local_path = Path(tmp) / f"upload{suffix}"
            local_path.write_bytes(raw)
            url = await store.upload(local_path, object_key)

        return UploadResponse(url=url, object_key=object_key, size_bytes=len(raw))

    return app


app = create_bridge_app()
