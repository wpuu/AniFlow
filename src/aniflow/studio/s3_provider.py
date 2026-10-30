"""Private S3 GameLift transport; never exposes ComfyUI or submits a second job."""
import hashlib
import json
import time
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from .s3_jobs import S3Jobs


class S3ComfyProvider:
    def __init__(self, client, bucket: str, prefix: str, session_key: str):
        self.client = client
        self.jobs = S3Jobs(client, bucket, prefix)
        self.session_key = session_key

    def connection_state(self):
        try:
            response = self.client.get_object(Bucket=self.jobs.bucket,
                                               Key=self.jobs.prefix + "/heartbeat.json")
            with response["Body"] as body:
                heartbeat = json.loads(body.read(1024 * 1024))
            connected = (heartbeat.get("session_key") == self.session_key
                         and 0 <= time.time() - heartbeat.get("observed_at_unix", 0) <= 30)
            return connected, connected and heartbeat.get("cuda_verified") is True
        except (BotoCoreError, ClientError, ValueError, TypeError):
            return False, False

    def upload(self, path: Path) -> str:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        name = digest + path.suffix
        try:
            self.client.put_object(Bucket=self.jobs.bucket,
                Key=self.jobs.prefix + "/inputs/" + name, Body=data,
                IfNoneMatch="*", ServerSideEncryption="AES256",
                Metadata={"sha256": digest})
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
                raise
        return name

    def submit(self, workflow: dict, request_key: str):
        request = {"workflow": workflow, "session_key": self.session_key}
        if not self.jobs.create_once(request_key, "request.json", request):
            previous = self.jobs.read(request_key, "request.json")
            if previous != request:
                raise ValueError("Durable request key belongs to another workflow")
        # The runtime alone owns the ComfyUI POST. No invented prompt ID.

    def inspect(self, prompt_id, request_key):
        submitted = self.jobs.read(request_key, "submitted.json") or {}
        prompt_id = submitted.get("prompt_id") or prompt_id
        if self.jobs.read(request_key, "result.json"):
            return prompt_id, "downloading", {"s3_request_key": request_key}
        if self.jobs.read(request_key, "failed.json"):
            return prompt_id, "failed", None
        if submitted:
            return prompt_id, "running", None
        if self.jobs.read(request_key, "claim.json"):
            return prompt_id, "submission_unknown", None
        if self.jobs.read(request_key, "request.json"):
            return prompt_id, "queued", None
        return prompt_id, "submission_unknown", None

    def download(self, history: dict, path: Path, profile=None):
        if profile != "h3_native_source":
            raise ValueError("GameLift results require the audited native source profile")
        result = self.jobs.download_result(history["s3_request_key"], path)
        return result["sha256"], result["bytes"], result["video"]
