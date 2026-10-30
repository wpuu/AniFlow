"""Restore one previously exported Wan final using S3 GETs only; never generate."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

from .comfy_provider import verify_mp4

MAX_REPORT_BYTES = 1024 * 1024
MAX_VIDEO_BYTES = 1024**3
FINAL_SPEC = {"width": 774, "height": 1376, "fps": 24, "frame_count": 120,
              "duration_seconds": 5, "sample_aspect_ratio": "1:1"}


def _validate_report(report: dict, experiment_id: str, prompt_id: str, request_key: str) -> dict:
    identity = {"experiment_id": experiment_id, "model": "wan2.2-i2v-a14b",
                "prompt_id": prompt_id, "request_key": request_key}
    if not isinstance(report, dict) or any(report.get(k) != v for k, v in identity.items()):
        raise ValueError("Wan report identity mismatch")
    media = report.get("media")
    final = media.get("final") if isinstance(media, dict) else None
    if not isinstance(final, dict):
        raise ValueError("Missing Wan final media manifest")  # noqa: TRY004 -- Invalid remote JSON value.
    size, digest, metadata = final.get("bytes"), final.get("sha256"), final.get("metadata")
    if (type(size) is not int or not 0 < size <= MAX_VIDEO_BYTES
            or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        raise ValueError("Invalid Wan final integrity manifest")
    if (not isinstance(metadata, dict)
            or any(metadata.get(k) != v or isinstance(metadata.get(k), bool)
                   for k, v in FINAL_SPEC.items())):
        raise ValueError("Invalid Wan final specification")
    return final


def _verify_local(path: Path, final: dict) -> tuple[str, int, dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Wan destination must be a regular file")
    if path.stat().st_size != final["bytes"]:
        raise ValueError("Wan MP4 byte count mismatch")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != final["sha256"]:
        raise ValueError("Wan MP4 SHA256 mismatch")
    metadata = verify_mp4(path, "wan_native_final")
    if any(metadata.get(k) != final["metadata"][k] for k in FINAL_SPEC):
        raise ValueError("Wan decoded metadata does not match its report")
    return digest.hexdigest(), final["bytes"], metadata


def restore_wan_output(client, *, region: str, bucket: str, experiment_id: str,
                       prompt_id: str, request_key: str,
                       destination: Path) -> tuple[str, int, dict]:
    """Download the exact final without re-encoding; matching existing files are reused.

    The caller supplies an already authenticated Ohio S3 client and persisted task identity.
    Network failures propagate so a later call can retry these same read-only object keys.
    Existing destination files are never replaced if any local integrity check fails.
    """
    if region != "us-east-2" or getattr(client.meta, "region_name", None) != region:
        raise ValueError("Wan restore requires an Ohio S3 client")
    for value, pattern in ((bucket, r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]"),
                           (experiment_id, r"aniflow-wan-ohio-20261027-[a-z0-9-]+"),
                           (prompt_id, r"[A-Za-z0-9_-]{1,128}"),
                           (request_key, r"[A-Za-z0-9_-]{8,128}")):
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise ValueError("Invalid Wan restore scope or task identity")
    prefix = f"experiments/{experiment_id}"
    response = client.get_object(Bucket=bucket, Key=f"{prefix}/reports/{prompt_id}.json")
    with response["Body"] as body:
        length = response.get("ContentLength")
        if type(length) is not int or not 0 < length <= MAX_REPORT_BYTES:
            raise ValueError("Invalid Wan report length")
        data = body.read(MAX_REPORT_BYTES + 1)
    if len(data) != length or len(data) > MAX_REPORT_BYTES:
        raise ValueError("Wan report length mismatch")
    final = _validate_report(json.loads(data), experiment_id, prompt_id, request_key)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        return _verify_local(destination, final)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = None
    try:
        response = client.get_object(Bucket=bucket, Key=f"{prefix}/outputs/{prompt_id}.mp4")
        with response["Body"] as source:
            if response.get("ContentLength") != final["bytes"]:
                raise ValueError("Wan MP4 response length mismatch")
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name + ".",
                                             suffix=".partial", delete=False) as target:
                partial = Path(target.name)
                count, digest = 0, hashlib.sha256()
                while block := source.read(1024 * 1024):
                    count += len(block)
                    if count > final["bytes"] or count > MAX_VIDEO_BYTES:
                        raise ValueError("Wan MP4 exceeds its manifest or the 1 GiB limit")
                    digest.update(block)
                    target.write(block)
        if count != final["bytes"] or digest.hexdigest() != final["sha256"]:
            raise ValueError("Wan MP4 byte count or SHA256 mismatch")
        result = _verify_local(partial, final)
        if destination.exists() or destination.is_symlink():
            return _verify_local(destination, final)
        partial.replace(destination)
        return result
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
