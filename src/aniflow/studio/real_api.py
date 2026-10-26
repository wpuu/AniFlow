"""Durable local H3 Bridge, disabled until a time-limited human audit is supplied."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse

from aniflow.studio.comfy_provider import ComfyProvider, postprocess_h3_portrait
from aniflow.studio.mock_api import JobRequest, create_mock_app

CHECKS = ("credit_ec2_eligible", "credit_expiry_confirmed", "tokyo_gpu_quota",
          "tokyo_capacity_and_price", "ssm_private_connectivity", "h3_license_territory",
          "gpu_stop_safeguard", "independent_stop_safeguard")
WORKSPACES_CHECKS = ("credit_workspaces_eligible", "credit_expiry_confirmed",
                     "tokyo_workspaces_quota", "tokyo_capacity_and_price",
                     "ssm_private_connectivity", "h3_license_territory",
                     "gpu_stop_safeguard", "independent_stop_safeguard",
                     "account_plan_unchanged", "workspaces_account_eligible")
GAMELIFT_CHECKS = ("credit_gamelift_eligible", "credit_expiry_confirmed", "tokyo_gamelift_quota",
                  "tokyo_capacity_and_price", "private_s3_connectivity", "h3_license_territory",
                  "gpu_stop_safeguard", "independent_stop_safeguard",
                  "account_plan_unchanged", "runtime_cuda_verified")
KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
SHA = re.compile(r"^[a-f0-9]{64}$")


@dataclass
class RealConfig:
    data_dir: Path
    comfy_url: str = "http://127.0.0.1:8188"
    gate_path: Path | None = None
    workflow_path: Path | None = None
    s3_bucket: str | None = None
    s3_session_key: str = ""

    @classmethod
    def from_environment(cls) -> RealConfig:
        def optional(name):
            return Path(os.environ[name]) if os.environ.get(name) else None
        return cls(Path(os.environ.get("ANIFLOW_REAL_DATA_DIR", "data/runtime/studio-real")),
                   os.environ.get("ANIFLOW_COMFY_URL", "http://127.0.0.1:8188"),
                   optional("ANIFLOW_REAL_GATE"), optional("ANIFLOW_H3_WORKFLOW"),
                   os.environ.get("ANIFLOW_GAMELIFT_BUCKET"),
                   os.environ.get("ANIFLOW_GAMELIFT_SESSION_KEY", ""))

    def audited_workflow(self) -> tuple[list[str], dict | None]:
        try:
            if not self.gate_path or not self.workflow_path:
                return ["A real AWS/license/dual-stop audit and pinned API workflow are required"], None
            gate = json.loads(self.gate_path.read_text(encoding="utf-8"))
            raw = self.workflow_path.read_bytes()
            bundle = json.loads(raw)
            if not isinstance(gate, dict) or not isinstance(bundle, dict):
                return ["Real audit and workflow must be JSON objects"], None
            source = bundle.get("source_url", "")
            allowed_source = isinstance(source, str) and source.startswith((
                "https://github.com/Comfy-Org/", "https://raw.githubusercontent.com/Comfy-Org/"))
            remaining = float(gate.get("expires_at_unix", 0)) - time.time()
            checks = gate.get("checks", {})
            service = gate.get("service", "ec2")
            if service == "gameliftstreams":
                resource_valid = (gate.get("instance_type") == "gen6n_pro"
                                  and 0 <= gate.get("cash_cap_usd", -1) <= 1
                                  and 0 < gate.get("credit_budget_usd", 0) <= 20
                                  and gate.get("s3_bucket") == self.s3_bucket
                                  and gate.get("session_key") == self.s3_session_key
                                  and bool(self.s3_session_key) and bool(self.s3_bucket))
                required_checks = GAMELIFT_CHECKS
            elif service == "workspaces":
                resource_valid = (gate.get("instance_type") == "Graphics.g6.4xlarge"
                                  and 0 <= gate.get("cash_cap_usd", -1) <= 1
                                  and 0 < gate.get("credit_budget_usd", 0) <= 20)
                required_checks = WORKSPACES_CHECKS
            else:
                resource_valid = (service == "ec2" and gate.get("instance_type") == "g6e.2xlarge"
                                  and 0 < gate.get("experiment_budget_usd", 0) <= 20)
                required_checks = CHECKS
            valid = (gate.get("launch_allowed") is True and 0 < remaining <= 4 * 3600
                     and gate.get("region") == "ap-northeast-1"
                     and resource_valid and isinstance(checks, dict)
                     and all(checks.get(name) is True for name in required_checks)
                     and gate.get("max_runtime_seconds", 0) in range(1, 14401)
                     and gate.get("workflow_sha256") == hashlib.sha256(raw).hexdigest()
                     and allowed_source and isinstance(bundle.get("prompt"), dict)
                     and bundle.get("bindings") and shutil.which("ffprobe")
                     and shutil.which("ffmpeg"))
            if not valid:
                return ["Real audit is blocked, expired, incomplete, or workflow tools/hash are invalid"], None
            if "postprocess" in bundle and bundle["postprocess"] != {"preset": "h3_native_5s_portrait_v1"}:
                return ["Unknown or invalid audited postprocess preset"], None
            if service in {"workspaces", "gameliftstreams"} and bundle.get("postprocess") != {"preset": "h3_native_5s_portrait_v1"}:
                return ["This H3 experiment requires the audited strict 5-second portrait preset"], None
            prompt = bundle["prompt"]
            if not prompt or not all(isinstance(node, dict) and "class_type" in node
                                     and isinstance(node.get("inputs"), dict)
                                     for node in prompt.values()):
                return ["Expected an audited ComfyUI API-format prompt"], None
            for field in ("image", "prompt"):
                node, input_name = bundle["bindings"][field]
                if input_name not in prompt[node]["inputs"]:
                    return ["Workflow binding does not exist in the pinned API prompt"], None
            return [], {**bundle, "_local_audit": gate}
        except (OSError, ValueError, TypeError, KeyError):
            return ["Real audit/workflow could not be validated"], None


def create_real_app(config: RealConfig | None = None,
                    transport: httpx.BaseTransport | None = None) -> FastAPI:
    cfg = config or RealConfig.from_environment()
    if cfg.s3_bucket:
        import boto3

        from .s3_provider import S3ComfyProvider
        session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name="ap-northeast-1")
        provider = S3ComfyProvider(session.client("s3"), cfg.s3_bucket,
                                  "experiments/h3-20261026", cfg.s3_session_key)
    else:
        provider = ComfyProvider(cfg.comfy_url, transport)
    base = cfg.data_dir.resolve()
    base.mkdir(parents=True, exist_ok=True)
    images, videos = base / "images", base / "videos"
    lock = threading.RLock()

    @contextmanager
    def connect():
        with sqlite3.connect(base / "tasks.sqlite3", timeout=10) as cx:
            cx.row_factory = sqlite3.Row
            cx.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, "
                       "request_key TEXT UNIQUE NOT NULL, payload_hash TEXT NOT NULL, data TEXT NOT NULL)")
            yield cx

    def save(job):
        with connect() as cx:
            cx.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(job), job["id"]))

    def jobs():
        with connect() as cx:
            return [json.loads(row["data"]) for row in cx.execute("SELECT data FROM jobs")]

    def get_job(job_id):
        with connect() as cx:
            row = cx.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown real job")
        return json.loads(row["data"])

    def refresh():
        with lock:
            for job in jobs():
                if job["status"] in {"completed", "failed", "submitting"}:
                    continue
                try:
                    prompt_id, status, history = provider.inspect(
                        job["comfy_prompt_id"], job["idempotency_key"])
                    job.update(comfy_prompt_id=prompt_id, status=status, error=None)
                    if history:
                        path = videos / (job["id"] + ".mp4")
                        if job.get("postprocess") == {"preset": "h3_native_5s_portrait_v1"}:
                            source = videos / (job["id"] + ".source.mp4")
                            source_digest, source_size, source_metadata = provider.download(
                                history, source, "h3_native_source")
                            job.update(source_local_path=str(source), source_sha256=source_digest,
                                       source_bytes=source_size, source_video_metadata=source_metadata)
                            save(job)
                            digest, size, metadata = postprocess_h3_portrait(source, path)
                        else:
                            digest, size, metadata = provider.download(history, path)
                        job.update(status="completed", verified=True, progress=100,
                                   output_sha256=digest, output_bytes=size,
                                   video_metadata=metadata, local_path=str(path),
                                   video_download_path=f"/api/studio/real/jobs/{job['id']}/video",
                                   elapsed_seconds=time.time() - job["created_at"])
                except (httpx.HTTPError, OSError, BotoCoreError, ClientError) as exc:
                    job["error"] = f"Read/download verification interrupted: {type(exc).__name__}; no resubmission"
                except (ValueError, KeyError, TypeError, StopIteration, ZeroDivisionError,
                        subprocess.SubprocessError) as exc:
                    job["status"] = "failed"
                    job["error"] = f"Media verification failed: {type(exc).__name__}; no resubmission"
                save(job)

    async def poll():
        while True:
            await asyncio.to_thread(refresh)
            await asyncio.sleep(2)

    @asynccontextmanager
    async def lifespan(app):
        for job in jobs():
            if job["status"] == "submitting":
                job["status"] = "submission_unknown"
                save(job)
        worker = asyncio.create_task(poll())
        try:
            yield
        finally:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            provider.client.close()

    app = FastAPI(title="AniFlow Real H3 Local Bridge", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["127.0.0.1", "localhost", "testserver"], www_redirect=False)

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin != str(request.base_url).rstrip("/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Cross-origin real submission is forbidden"}, status_code=403)
        return await call_next(request)

    @app.get("/api/studio/real/health")
    def health():
        reasons, _ = cfg.audited_workflow()
        tunnel_connected, gpu_connected = provider.connection_state()
        if not tunnel_connected:
            reasons.append("Private S3 runtime heartbeat is unavailable" if cfg.s3_bucket
                           else "ComfyUI loopback tunnel is unavailable")
        elif not gpu_connected:
            reasons.append("ComfyUI system stats do not report a CUDA GPU with positive VRAM")
        return {"mode": "REAL_H3", "provider": "minimax-h3", "simulation": False,
                "ready": not reasons, "tunnel_connected": tunnel_connected,
                "gpu_connected": gpu_connected, "blocked_reasons": reasons,
                "note": "Tunnel connectivity alone does not verify GPU, license, credit, or shutdown protection"}

    @app.get("/api/studio/cloud/preflight")
    def preflight():
        reasons, bundle = cfg.audited_workflow()
        audit = bundle["_local_audit"] if bundle else {}
        service = audit.get("service", "ec2") if audit else (
            "gameliftstreams" if cfg.s3_bucket else "workspaces")
        workspaces = service == "workspaces"
        gamelift = service == "gameliftstreams"
        tunnel_connected, gpu_connected = provider.connection_state()
        if not tunnel_connected:
            reasons.append("Private S3 runtime heartbeat is unavailable" if gamelift
                           else "ComfyUI loopback tunnel is unavailable")
        elif not gpu_connected:
            reasons.append("ComfyUI system stats do not report a CUDA GPU with positive VRAM")

        def number(name):
            value = audit.get(name)
            return value if type(value) in (int, float) and math.isfinite(value) else None

        checks = GAMELIFT_CHECKS if gamelift else (WORKSPACES_CHECKS if workspaces else CHECKS)
        return {"mode": "LOCAL_AUDIT_PROJECTION", "service": service, "region": "ap-northeast-1",
                "instance_type": "gen6n_pro" if gamelift else ("Graphics.g6.4xlarge" if workspaces else "g6e.2xlarge"),
                "expected_gpu": "NVIDIA L4" if workspaces or gamelift else None,
                "expected_gpu_vram_gib": 24 if workspaces or gamelift else None,
                "expected_ram_gib": 64 if workspaces or gamelift else None,
                "account_plan": audit.get("account_plan") if isinstance(audit.get("account_plan"), str)
                                and audit["account_plan"] else "unknown",
                "estimated_credit_remaining_usd": number("estimated_credit_remaining_usd"),
                "credit_settled_remaining_usd": number("credit_settled_remaining_usd"),
                "credit_observed_at_utc": audit.get("credit_observed_at_utc")
                                         if isinstance(audit.get("credit_observed_at_utc"), str) else None,
                "hourly_price_usd": number("hourly_price_usd"),
                "checks": {name: audit["checks"][name] if audit else None for name in checks},
                "launch_allowed": not reasons, "real_gpu_connected": gpu_connected,
                "tunnel_connected": tunnel_connected, "aws_queries": 1 if gamelift else 0, "aws_writes": 0,
                "blocked_reasons": reasons,
                "note": ("Account checks are a local audit snapshot; connection reads a live private S3 heartbeat. "
                        if gamelift else "Local validated audit projection only; no live AWS query. ")
                        + "Expected hardware is not observed hardware. "
                        "ComfyUI connectivity does not establish AWS account, credit, capacity, or shutdown evidence."}

    @app.post("/api/studio/real/assets")
    async def upload(file: Annotated[UploadFile, File(...)]):
        raw = await file.read(10 * 1024 * 1024 + 1)
        if not 12 <= len(raw) <= 10 * 1024 * 1024:
            raise HTTPException(413, "Image must be non-empty and at most 10 MiB")
        suffix = ".png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else (
            ".jpg" if raw.startswith(b"\xff\xd8\xff") else None)
        if suffix is None:
            raise HTTPException(415, "Only PNG/JPEG first frames are accepted")
        digest = hashlib.sha256(raw).hexdigest()
        images.mkdir(exist_ok=True)
        (images / (digest + suffix)).write_bytes(raw)
        return {"image_id": digest, "sha256": digest, "bytes": len(raw), "simulation": False}

    def image_path(image_id):
        if SHA.fullmatch(image_id):
            for suffix in (".png", ".jpg"):
                path = images / (image_id + suffix)
                if path.is_file():
                    return path
        raise HTTPException(404, "Unknown local real first frame")

    @app.get("/api/studio/real/assets/{image_id}")
    def image(image_id: str):
        return FileResponse(image_path(image_id), headers={"Cache-Control": "no-store"})

    @app.post("/api/studio/real/jobs", status_code=202)
    def create_job(task: JobRequest):
        if (task.provider != "minimax-h3" or task.duration_seconds != 5
                or task.aspect_ratio != "9:16" or not KEY.fullmatch(task.idempotency_key)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task.project_id)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task.shot_id)):
            raise HTTPException(422, "Real H3 requires a valid ID and one 5-second 9:16 job")
        payload = task.model_dump()
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with lock, connect() as cx:
            row = cx.execute("SELECT * FROM jobs WHERE request_key=?", (task.idempotency_key,)).fetchone()
            if row:
                if row["payload_hash"] != digest:
                    raise HTTPException(409, "Idempotency key belongs to a different request")
                return json.loads(row["data"])
            reasons, bundle = cfg.audited_workflow()
            if reasons:
                raise HTTPException(403, "; ".join(reasons))
            _, gpu_connected = provider.connection_state()
            if not gpu_connected:
                raise HTTPException(403, "Real submission requires an observed CUDA GPU")
            if cx.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]:
                raise HTTPException(409, "The first experiment permits one real submission only")
            source = image_path(task.image_id)
            job = {**payload, "id": "real-" + uuid4().hex, "status": "submitting",
                   "created_at": time.time(), "simulation": False, "gpu_connected": gpu_connected,
                   "progress": None, "comfy_prompt_id": None, "local_path": None,
                   "output_sha256": None, "output_bytes": None, "video_metadata": None,
                   "source_local_path": None, "source_sha256": None, "source_bytes": None,
                   "source_video_metadata": None, "postprocess": bundle.get("postprocess"),
                   "verified": False, "elapsed_seconds": None, "peak_vram_mb": None,
                   "actual_cost_usd": None, "video_download_path": None, "error": None}
            cx.execute("INSERT INTO jobs VALUES (?,?,?,?)", (job["id"], task.idempotency_key,
                                                            digest, json.dumps(job)))
        with lock:
            try:
                uploaded_name = provider.upload(source)
                prompt = json.loads(json.dumps(bundle["prompt"]))
                for field, value in (("image", uploaded_name), ("prompt", task.prompt),
                                     ("negative_prompt", task.negative_prompt)):
                    if field in bundle["bindings"]:
                        node, input_name = bundle["bindings"][field]
                        prompt[node]["inputs"][input_name] = value
                # The unknown state is committed BEFORE the only chargeable POST.
                job["status"] = "submission_unknown"
                save(job)
                prompt_id = provider.submit(prompt, task.idempotency_key)
                job.update(comfy_prompt_id=prompt_id, status="queued")
            except (httpx.HTTPError, ValueError, OSError, KeyError, TypeError,
                    BotoCoreError, ClientError) as exc:
                job["error"] = f"Submission outcome uncertain: {type(exc).__name__}; no automatic resubmission"
                job["status"] = "submission_unknown"
            save(job)
        return job

    @app.get("/api/studio/real/requests/{request_key}")
    def recover(request_key: str):
        refresh()
        with connect() as cx:
            row = cx.execute("SELECT data FROM jobs WHERE request_key=?", (request_key,)).fetchone()
        if row is None:
            raise HTTPException(404, "Request not indexed; do not resubmit")
        return json.loads(row["data"])

    @app.get("/api/studio/real/jobs")
    def list_jobs(limit: int = 50):
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Invalid list limit")
        refresh()
        return {"jobs": sorted(jobs(), key=lambda job: job["created_at"], reverse=True)[:limit],
                "simulation": False}

    @app.get("/api/studio/real/jobs/{job_id}")
    def status(job_id: str):
        refresh()
        return get_job(job_id)

    @app.get("/api/studio/real/jobs/{job_id}/video")
    def video(job_id: str):
        job = get_job(job_id)
        path = videos / (job_id + ".mp4")
        if not job["verified"] or job["status"] != "completed":
            raise HTTPException(409, "Real output is not downloaded and verified")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != job["output_sha256"]:
            raise HTTPException(409, "Local real MP4 hash no longer matches")
        return FileResponse(path, media_type="video/mp4", filename=path.name,
                            headers={"Cache-Control": "no-store", "X-AniFlow-Simulation": "false"})

    # Reuse only read-only presentation routes; do not expose mock creation on this service.
    mock = create_mock_app(data_dir=base / "unused-mock")
    for route in mock.routes:
        if getattr(route, "path", None) in {"/", "/images/logo.png"}:
            app.router.routes.append(route)
    return app
