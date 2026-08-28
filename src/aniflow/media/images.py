from __future__ import annotations

import tempfile
from pathlib import Path

from aniflow.media.download import download_file
from aniflow.media.store import PublicMediaStore


def detect_image_suffix(path: Path) -> str:
    header = path.read_bytes()[:16]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


async def persist_remote_image(
    *,
    media_store: PublicMediaStore,
    source_url: str,
    object_key_without_suffix: str,
) -> str:
    with tempfile.TemporaryDirectory(prefix="aniflow-image-") as tmp:
        raw = await download_file(
            source_url,
            Path(tmp) / "source.bin",
            timeout_seconds=360.0,
        )
        suffix = detect_image_suffix(raw)
        local = raw.with_suffix(suffix)
        raw.replace(local)
        return await media_store.upload(local, f"{object_key_without_suffix}{suffix}")
