"""AniFlow local-only H3/ComfyUI contract simulator.

No AWS SDK, no Agnes key, no network requests and no paid generation.
Task IDs, image assets and fake MP4 results are durable on local disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from zipfile import ZipFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
MOCK_VIDEO = ROOT / "tests/fixtures/MOCK_BLUE_LOCAL_NO_AGNES.mp4"
MOCK_FRONTEND = ROOT / "apps/studio-mock-ui/dist/index.html"
GROK_SOURCE_ZIP = ROOT / "aniflow-ai-video-dashboard-grok.zip"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

class JobRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    shot_id: str = Field(min_length=1, max_length=64)
    image_id: str = Field(min_length=64, max_length=64)
    prompt: str = Field(min_length=1, max_length=5000)
    negative_prompt: str = Field(default="", max_length=3000)
    duration_seconds: int = Field(default=5, ge=1, le=15)
    aspect_ratio: str = Field(default="9:16")
    idempotency_key: str = Field(min_length=8, max_length=128)
    provider: str = Field(default="mock-h3")

def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def create_mock_app(
    data_dir: Path | None = None,
    fixture_path: Path | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    base = (data_dir or (Path.cwd() / "data/runtime/studio")).resolve()
    fixture = fixture_path or MOCK_VIDEO
    now = clock or time.time
    app = FastAPI(title="AniFlow Mock H3 (NO GPU)", version="0.0.1-mock")
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
        www_redirect=False,
    )
    db = base / "tasks.sqlite3"
    uploads = base / "images"
    videos = base / "videos"

    @contextmanager
    def connect() -> Iterator[sqlite3.Connection]:
        base.mkdir(parents=True, exist_ok=True)
        cx = sqlite3.connect(db, timeout=10)
        try:
            cx.execute(
                "CREATE TABLE IF NOT EXISTS jobs ("
                "id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,"
                "payload_hash TEXT NOT NULL, data TEXT NOT NULL,"
                "created_at REAL NOT NULL)"
            )
            cx.row_factory = sqlite3.Row
            yield cx
            cx.commit()
        except BaseException:
            cx.rollback()
            raise
        finally:
            cx.close()

    def status_for(row: sqlite3.Row) -> dict:
        entry = json.loads(row["data"])
        age = max(0.0, now() - row["created_at"])
        status = "queued" if age < 1 else "running" if age < 6 else "completed"
        progress = 0 if status == "queued" else min(95, int((age - 1) / 5 * 100))
        video_path = videos / (entry["id"] + ".mp4")
        sha = None
        if status == "completed":
            if not fixture.is_file():
                raise HTTPException(503, "Local marked MOCK MP4 fixture unavailable")
            videos.mkdir(parents=True, exist_ok=True)
            expected = _hash(fixture.read_bytes())
            if not video_path.is_file() or _hash(video_path.read_bytes()) != expected:
                tmp = videos / (entry["id"] + ".partial-" + uuid4().hex)
                try:
                    shutil.copyfile(fixture, tmp)
                    if _hash(tmp.read_bytes()) != expected:
                        raise HTTPException(500, "Mock video copy hash mismatch")
                    os.replace(tmp, video_path)
                finally:
                    tmp.unlink(missing_ok=True)
            sha = expected
            progress = 100
        return {
            **entry,
            "status": status,
            "progress": progress,
            "simulation": True,
            "gpu_connected": False,
            "actual_cost_usd": 0.0,
            "output_sha256": sha,
            "video_download_path": f"/api/studio/mock/jobs/{entry['id']}/video" if sha else None,
        }

    def get_row(job_id: str) -> sqlite3.Row:
        with connect() as cx:
            row = cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown mock job")
        return row

    @app.get("/", include_in_schema=False)
    def mock_frontend():
        if not MOCK_FRONTEND.is_file():
            return JSONResponse(status_code=503, content={
                "mode": "MOCK_ONLY",
                "message": "Build apps/studio-mock-ui frontend before opening this page",
            })
        return FileResponse(
            MOCK_FRONTEND, media_type="text/html",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    @app.get("/images/logo.png", include_in_schema=False)
    def mock_logo():
        with ZipFile(GROK_SOURCE_ZIP) as z:
            logo = z.read("public/images/logo.png")
        if not (1000 <= len(logo) < 2_000_000) or not logo.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(500, "Original Grok logo is invalid")
        return Response(content=logo, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/studio/cloud/preflight")
    def cloud_preflight() -> dict:
        """Non-authoritative UI contract. This route NEVER contacts AWS or creates EC2."""
        return {
            "mode": "UNVERIFIED_PLACEHOLDER",
            "provider": "minimax-h3-aws",
            "region": "ap-northeast-1",
            "instance_type": "g6e.2xlarge",
            "account_plan": "unknown",
            "checks": {
                "credit_ec2_eligible": None,
                "credit_expiry_confirmed": None,
                "tokyo_gpu_quota": None,
                "tokyo_capacity_and_price": None,
                "ssm_private_connectivity": None,
                "h3_license_territory": None,
                "gpu_stop_safeguard": None,
            },
            "actual_credit_usd": None,
            "hourly_price_usd": None,
            "instance_id": None,
            "launch_allowed": False,
            "real_gpu_connected": False,
            "aws_queries": 0,
            "aws_writes": 0,
            "note": "Only a local UI placeholder; switch to Work to audit the real AWS account.",
        }

    @app.get("/api/studio/mock/health")
    def health() -> dict:
        return {
            "mode": "MOCK_ONLY",
            "provider": "mock-h3",
            "aws_state": "NOT_CONNECTED",
            "comfyui_state": "NOT_CONNECTED",
            "paid_request_count": 0,
            "real_generation_count": 0,
        }

    @app.post("/api/studio/mock/assets")
    async def add_image(file: Annotated[UploadFile, File(...)]) -> dict:
        content = await file.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES or len(content) < 12:
            raise HTTPException(413, "Image too large or empty")
        ext = ".png" if content.startswith(b"\x89PNG\r\n\x1a\n") else (
            ".jpg" if content.startswith(b"\xff\xd8\xff") else None
        )
        if ext is None:
            raise HTTPException(415, "Only PNG/JPEG image files")
        digest = _hash(content)
        uploads.mkdir(parents=True, exist_ok=True)
        dest = uploads / (digest + ext)
        if not dest.exists():
            dest.write_bytes(content)
        return {"image_id": digest, "sha256": digest, "bytes": len(content),
                "simulation": True}

    @app.get("/api/studio/mock/assets/{image_id}")
    def get_image(image_id: str):
        if not re.fullmatch(r"[a-f0-9]{64}", image_id):
            raise HTTPException(404, "Unknown image")
        for ext, mimetype in ((".png", "image/png"), (".jpg", "image/jpeg")):
            path = uploads / (image_id + ext)
            if path.is_file():
                return FileResponse(
                    path, media_type=mimetype,
                    headers={"Cache-Control": "no-store"},
                )
        raise HTTPException(404, "Unknown image")

    @app.post("/api/studio/mock/jobs", status_code=202)
    def create_job(task: JobRequest) -> dict:
        if task.provider != "mock-h3":
            raise HTTPException(422, "Real AWS generation is not enabled")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", task.idempotency_key):
            raise HTTPException(422, "Invalid idempotency key")
        if not LABEL_RE.fullmatch(task.project_id) or not LABEL_RE.fullmatch(task.shot_id):
            raise HTTPException(422, "Unsafe project/shot ID")
        if task.aspect_ratio not in ("9:16", "16:9", "1:1"):
            raise HTTPException(422, "Unsupported mock aspect ratio")
        if not re.fullmatch(r"[a-f0-9]{64}", task.image_id):
            raise HTTPException(422, "Invalid image SHA")
        if not any((uploads / (task.image_id + ext)).is_file() for ext in (".png", ".jpg")):
            raise HTTPException(422, "Image was not uploaded to local Bridge")
        serialized = task.model_dump()
        payload_hash = _hash(json.dumps(serialized, ensure_ascii=False, sort_keys=True).encode())
        job = {
            "id": "mock-" + uuid4().hex,
            "project_id": task.project_id,
            "shot_id": task.shot_id,
            "prompt": task.prompt,
            "negative_prompt": task.negative_prompt,
            "image_id": task.image_id,
            "duration_seconds": task.duration_seconds,
            "aspect_ratio": task.aspect_ratio,
            "provider": "mock-h3",
            "created_at": now(),
        }
        with connect() as cx:
            cx.execute(
                "INSERT OR IGNORE INTO jobs(id,idempotency_key,payload_hash,data,created_at)"
                " VALUES (?,?,?,?,?)",
                (job["id"], task.idempotency_key, payload_hash,
                 json.dumps(job, ensure_ascii=False), job["created_at"]),
            )
            row = cx.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (task.idempotency_key,)
            ).fetchone()
            if row is None:
                raise HTTPException(500, "Failed to commit mock job")
            if row["payload_hash"] != payload_hash:
                raise HTTPException(409, "Idempotency key reused for different payload")
        return status_for(row)

    @app.get("/api/studio/mock/requests/{request_key}")
    def get_submission_by_key(request_key: str) -> dict:
        """Read-only recovery after POST response loss; never create a second job."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_key):
            raise HTTPException(404, "Unknown request key")
        with connect() as cx:
            row = cx.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (request_key,)
            ).fetchone()
        if row is None:
            # A preceding POST might still be processing: 404 is NOT proof of rejection.
            raise HTTPException(404, "Request not indexed yet; do not auto-resubmit")
        return status_for(row)

    @app.get("/api/studio/mock/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        return status_for(get_row(job_id))

    @app.get("/api/studio/mock/jobs")
    def list_jobs(limit: int = 50) -> dict:
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Invalid list limit")
        with connect() as cx:
            rows = cx.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return {"jobs": [status_for(row) for row in rows], "simulation": True}

    @app.get("/api/studio/mock/jobs/{job_id}/video")
    def get_video(job_id: str):
        current = status_for(get_row(job_id))
        if current["status"] != "completed":
            raise HTTPException(409, "Mock job is not completed")
        path = videos / (job_id + ".mp4")
        if not path.is_file() or _hash(path.read_bytes()) != current["output_sha256"]:
            raise HTTPException(500, "Local MP4 hash verification failed")
        return FileResponse(path, media_type="video/mp4",
                            filename=f"{current['project_id']}-{current['shot_id']}-MOCK.mp4",
                            headers={"Cache-Control": "no-store", "X-AniFlow-Simulation": "true"})

    return app
