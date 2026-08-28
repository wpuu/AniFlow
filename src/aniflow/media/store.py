from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

import boto3

from aniflow.config import Settings


class PublicMediaStore:
    """S3-compatible uploader that returns stable public HTTPS URLs.

    Cloudflare R2 is the recommended deployment, but any S3-compatible endpoint
    with a public/custom domain works.
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

        def _upload() -> None:
            self._client.upload_file(
                str(path),
                self.settings.s3_bucket,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )

        await asyncio.to_thread(_upload)
        return f"{self.settings.s3_public_base_url.rstrip('/')}/{object_key.lstrip('/')}"
