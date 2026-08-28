from __future__ import annotations

from dataclasses import dataclass

from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.pipeline.storyboard import Storyboard3


@dataclass(frozen=True, slots=True)
class KeyframeSet:
    frame_a_url: str
    frame_b_url: str
    frame_c_url: str


class KeyframeGenerator:
    """Generate A/B/C while carrying character identity, style, and previous-frame context forward."""

    def __init__(self, key_pool: KeyPool, image_client: AgnesImageClient) -> None:
        self.key_pool = key_pool
        self.image_client = image_client

    async def generate_three(
        self,
        *,
        storyboard: Storyboard3,
        character_reference_urls: list[str],
        style: str,
    ) -> KeyframeSet:
        refs = [url.strip() for url in character_reference_urls if url.strip()]
        if not refs:
            raise ValueError("At least one character reference image URL is required")
        selected_style = style.strip()
        if not selected_style:
            raise ValueError("Visual style must not be empty")

        frame_a_url = await self._generate(
            prompt=(
                f"{storyboard.frame_a.image_prompt}\n\n"
                "Reference roles: the supplied images define the exact canonical character identity, "
                "materials, colors, accessories and proportions. "
                f"Create keyframe A as a vertical 9:16 animation frame in this exact visual style: {selected_style}. "
                "Preserve identity exactly. Do not introduce a different rendering medium. "
                "No text or watermark."
            ),
            references=refs,
        )

        frame_b_url = await self._generate(
            prompt=(
                f"{storyboard.frame_b.image_prompt}\n\n"
                "Reference roles: the first reference image(s) define the canonical character. "
                "The final reference image is keyframe A and defines the established scene, camera, "
                "lighting and material language. "
                f"Create keyframe B in the same exact visual style: {selected_style}. "
                "Preserve the same character identity and scene continuity. B must be a clean, "
                "stable composition that can serve both as an ending frame and the next starting frame. "
                "Do not introduce a different rendering medium. No text or watermark."
            ),
            references=[*refs[:3], frame_a_url],
        )

        frame_c_url = await self._generate(
            prompt=(
                f"{storyboard.frame_c.image_prompt}\n\n"
                "Reference roles: the first reference image(s) define the canonical character. "
                "The final reference image is keyframe B and defines the immediately previous scene state. "
                f"Create keyframe C in the same exact visual style: {selected_style}. "
                "Preserve identity, materials, accessories, lighting logic and environment continuity exactly. "
                "Do not introduce a different rendering medium. No text or watermark."
            ),
            references=[*refs[:3], frame_b_url],
        )

        return KeyframeSet(
            frame_a_url=frame_a_url,
            frame_b_url=frame_b_url,
            frame_c_url=frame_c_url,
        )

    async def _generate(self, *, prompt: str, references: list[str]) -> str:
        slot = await self.key_pool.next()
        image = await self.image_client.generate(
            api_key=slot.api_key,
            prompt=prompt,
            size="1K",
            ratio="9:16",
            reference_images=references,
        )
        if not image.url:
            raise RuntimeError("Agnes Image 2.1 Flash returned no URL")
        return image.url
