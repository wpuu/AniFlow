"""Private, durable job handoff. An existing claim never authorizes another POST."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from botocore.exceptions import ClientError


class S3Jobs:
    def __init__(self, client, bucket: str, prefix: str):
        if not re.fullmatch(r"aniflow-h3-[a-z0-9-]+", bucket):
            raise ValueError("An experiment-specific private bucket is required")
        if not re.fullmatch(r"experiments/[a-zA-Z0-9_-]+", prefix):
            raise ValueError("Invalid experiment prefix")
        self.client, self.bucket, self.prefix = client, bucket, prefix

    def _key(self, request_key: str, name: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", request_key):
            raise ValueError("Invalid durable request key")
        return f"{self.prefix}/jobs/{request_key}/{name}"

    def read(self, request_key: str, name: str) -> dict | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(request_key, name))
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                return None
            raise
        with response["Body"] as body:
            data = body.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Job metadata exceeds 1 MiB")
        return json.loads(data)

    def create_once(self, request_key: str, name: str, value: dict) -> bool:
        body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        if len(body) > 1024 * 1024:
            raise ValueError("Job metadata exceeds 1 MiB")
        try:
            self.client.put_object(Bucket=self.bucket, Key=self._key(request_key, name), Body=body,
                IfNoneMatch="*", ContentType="application/json", ServerSideEncryption="AES256",
                ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode())
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"PreconditionFailed", "412"}:
                return False
            # Conflict, network timeout or 5xx is uncertain; never retry a POST downstream.
            raise

    def submit_once(self, request_key: str, workflow: dict, provider, session_id: str) -> dict:
        digest = hashlib.sha256(json.dumps(workflow, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()
        claim = {"workflow_sha256": digest, "session_id": session_id}
        acquired = self.create_once(request_key, "claim.json", claim)
        if not acquired:
            previous = self.read(request_key, "claim.json")
            if previous is None or previous.get("workflow_sha256") != digest:
                raise ValueError("Request key conflicts with a different workflow")
            return self.read(request_key, "submitted.json") or {"state": "submission_unknown"}
        # Claim is durable before the only allowed POST. Exceptions leave it closed.
        prompt_id = provider.submit(workflow, request_key)
        submitted = {"state": "submitted", "prompt_id": prompt_id, **claim}
        self.create_once(request_key, "submitted.json", submitted)
        return submitted

    def download_result(self, request_key: str, path: Path) -> dict:
        manifest = self.read(request_key, "result.json")
        key = self._key(request_key, "source.mp4")
        if not manifest or manifest.get("key") != key:
            raise ValueError("No trusted result manifest for this task")
        size = manifest.get("bytes")
        digest = manifest.get("sha256")
        if (type(size) is not int or not 0 < size <= 1024**3
                or not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest)):
            raise ValueError("Invalid MP4 integrity manifest")
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".mp4.partial")
        actual, count = hashlib.sha256(), 0
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            with response["Body"] as source, partial.open("wb") as target:
                while block := source.read(1024 * 1024):
                    count += len(block)
                    if count > size:
                        raise ValueError("MP4 is larger than its manifest")
                    actual.update(block)
                    target.write(block)
            if count != size or actual.hexdigest() != digest:
                raise ValueError("MP4 byte count or SHA256 mismatch")
            from .comfy_provider import verify_mp4
            metadata = verify_mp4(partial, "h3_native_source")
            partial.replace(path)
            return {"bytes": count, "sha256": digest, "video": metadata}
        finally:
            partial.unlink(missing_ok=True)
