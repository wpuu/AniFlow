from __future__ import annotations

from dataclasses import dataclass

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.config import Settings


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    url: str | None
    b64_json: str | None
    revised_prompt: str | None


class AgnesImageClient:
    def __init__(self, settings: Settings, http: AgnesHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def generate(
        self,
        *,
        api_key: str,
        prompt: str,
        size: str | None = None,
        ratio: str | None = None,
        reference_images: list[str] | None = None,
        return_base64: bool = False,
    ) -> GeneratedImage:
        payload: dict = {
            "model": self.settings.agnes_image_model,
            "prompt": prompt,
            "size": size or self.settings.aniflow_image_size,
            "ratio": ratio or self.settings.aniflow_aspect_ratio,
        }
        if return_base64:
            payload["return_base64"] = True
        else:
            payload["extra_body"] = {"response_format": "url"}

        if reference_images:
            extra = payload.setdefault("extra_body", {})
            extra["image"] = reference_images
            extra["response_format"] = "b64_json" if return_base64 else "url"

        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/images/generations",
            api_key=api_key,
            json=payload,
        )
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise AgnesApiError("Agnes image response did not contain data[0]")
        first = items[0]
        if not isinstance(first, dict):
            raise AgnesApiError("Agnes image data[0] is not an object")
        return GeneratedImage(
            url=first.get("url"),
            b64_json=first.get("b64_json"),
            revised_prompt=first.get("revised_prompt"),
        )
