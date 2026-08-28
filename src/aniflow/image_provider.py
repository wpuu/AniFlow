from __future__ import annotations

from typing import Protocol

from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.key_pool import KeyPool


class ImageProvider(Protocol):
    """Provider-neutral image generation interface used by AniFlow pipelines.

    A provider may be a direct API (Agnes) or a controlled external application
    adapter (for example CapCut/Seedream). Pipelines only require a public image
    URL and do not need to know how the image was produced.
    """

    async def generate(
        self,
        *,
        prompt: str,
        references: list[str],
        size: str = "1K",
        ratio: str = "9:16",
    ) -> str: ...


class AgnesImageProvider:
    """Default ImageProvider backed by Agnes Image and the configured key pool."""

    def __init__(self, key_pool: KeyPool, image_client: AgnesImageClient) -> None:
        self.key_pool = key_pool
        self.image_client = image_client

    async def generate(
        self,
        *,
        prompt: str,
        references: list[str],
        size: str = "1K",
        ratio: str = "9:16",
    ) -> str:
        slot = await self.key_pool.next()
        image = await self.image_client.generate(
            api_key=slot.api_key,
            prompt=prompt,
            size=size,
            ratio=ratio,
            reference_images=references or None,
        )
        if not image.url:
            raise RuntimeError("Agnes Image returned no public URL")
        return image.url
