from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

import boto3

from aniflow.config import Settings


class PublicMediaStore:
    """S3-compatible public media storage.

    Cloudflare R2 is the recommended deployment, but any S3-compatible endpoint
    with a public/custom domain works. Permanent assets use stable object keys;
    short-lived visual-QA assets can be deleted after judging.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.s3_ready:
            raise ValueError("S3/R2 media storage is not fully configured")
        self.settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )

    async def upload(self, local_path: Path, object_key: str) -> str:
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        normalized_key = object_key.lstrip("/")

        def _upload() -> None:
            self._client.upload_file(
                str(path),
                self.settings.s3_bucket,
                normalized_key,
                ExtraArgs={"ContentType": content_type},
            )

        await asyncio.to_thread(_upload)
        return f"{self.settings.s3_public_base_url.rstrip('/')}/{normalized_key}"

    async def delete(self, object_key: str) -> None:
        normalized_key = object_key.lstrip("/")
        if not normalized_key:
            raise ValueError("object_key must not be empty")

        def _delete() -> None:
            self._client.delete_object(
                Bucket=self.settings.s3_bucket,
                Key=normalized_key,
            )

        await asyncio.to_thread(_delete)

    async def delete_many(self, object_keys: list[str]) -> None:
        keys = [key.lstrip("/") for key in object_keys if key.strip()]
        if not keys:
            return

        def _delete_many() -> None:
            self._client.delete_objects(
                Bucket=self.settings.s3_bucket,
                Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
            )

        await asyncio.to_thread(_delete_many)
