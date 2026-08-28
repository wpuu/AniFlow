from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.agnes.image import AgnesImageClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.config import Settings
from aniflow.image_provider import AgnesImageProvider, ImageProvider
from aniflow.media.download import download_file
from aniflow.media.images import persist_remote_image
from aniflow.media.store import PublicMediaStore
from aniflow.styles import resolve_style


class CharacterBible(BaseModel):
    character_id: str
    display_name: str
    species_or_type: str
    body_shape: str
    proportions: str
    primary_colors: list[str]
    face_and_eyes: str
    accessory: str
    distinguishing_feature: str
    personality_visual_cues: list[str] = Field(default_factory=list)
    locked_traits: list[str] = Field(default_factory=list)

    def identity_prompt(self) -> str:
        locked = "; ".join(self.locked_traits)
        colors = ", ".join(self.primary_colors)
        cues = ", ".join(self.personality_visual_cues)
        return (
            f"Character: {self.display_name}; type: {self.species_or_type}; body: {self.body_shape}; "
            f"proportions: {self.proportions}; colors: {colors}; face/eyes: {self.face_and_eyes}; "
            f"accessory: {self.accessory}; distinguishing feature: {self.distinguishing_feature}; "
            f"visual personality cues: {cues}. Locked traits: {locked}."
        )


class CharacterReferenceSet(BaseModel):
    character_id: str
    style_key: str
    style_description: str
    bible: CharacterBible
    identity_anchor_url: str | None = None
    front_url: str
    three_quarter_url: str
    side_url: str

    @property
    def urls(self) -> list[str]:
        return [self.front_url, self.three_quarter_url, self.side_url]


class CharacterBuilder:
    def __init__(
        self,
        *,
        settings: Settings,
        key_pool: KeyPool,
        http: AgnesHttpClient,
        image_client: AgnesImageClient | None,
        media_store: PublicMediaStore,
        image_provider: ImageProvider | None = None,
    ) -> None:
        self.settings = settings
        self.key_pool = key_pool
        self.http = http
        self.media_store = media_store
        if image_provider is not None:
            self.image_provider = image_provider
        elif image_client is not None:
            self.image_provider = AgnesImageProvider(key_pool, image_client)
        else:
            raise ValueError("image_client is required when image_provider is not supplied")

    async def create_bible(
        self,
        *,
        character_id: str,
        display_name: str,
        description: str,
    ) -> CharacterBible:
        slot = await self.key_pool.next()
        instruction = f"""
Create a strict reusable visual character bible for an AI animation pipeline.

ID: {character_id}
Name: {display_name}
Owner description: {description}

The design must be simple enough for reliable keyframe animation. Favor a highly recognizable silhouette, one accessory, one distinguishing feature, simple colors, short limbs, and no intricate patterns. Do not add text or logos.

Return JSON only:
{{
  "character_id": "{character_id}",
  "display_name": "{display_name}",
  "species_or_type": "",
  "body_shape": "",
  "proportions": "",
  "primary_colors": [""],
  "face_and_eyes": "",
  "accessory": "",
  "distinguishing_feature": "",
  "personality_visual_cues": [""],
  "locked_traits": [""]
}}
""".strip()
        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/chat/completions",
            api_key=slot.api_key,
            json={
                "model": self.settings.agnes_text_model,
                "messages": [{"role": "user", "content": instruction}],
                "temperature": 0.35,
                "max_tokens": 1600,
            },
        )
        try:
            text = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesApiError("Character bible response missing assistant content") from exc
        return CharacterBible.model_validate(self._parse_json(text))

    async def build_identity_anchor(self, *, bible: CharacterBible) -> str:
        """Create one cross-style geometry/identity anchor shared by every style benchmark."""
        identity = bible.identity_prompt()
        source_url = await self._generate_image(
            prompt=(
                f"{identity}\n"
                "Create a canonical full-body FRONT identity anchor for an animation character. "
                "The purpose is to lock silhouette, head-to-body ratio, limb length, face placement, colors, "
                "accessory shape and distinguishing feature before later style conversion. Use a simple neutral "
                "matte studio maquette appearance with minimal generic material cues: not wool/felt, not clay, "
                "and not a finished toy style. Centered neutral standing pose, arms and legs clearly separated, "
                "plain neutral background, soft even lighting, vertical 9:16. No text, labels or watermark."
            ),
            references=[],
        )
        return await persist_remote_image(
            media_store=self.media_store,
            source_url=source_url,
            object_key_without_suffix=(
                f"aniflow/characters/{self._slug(bible.character_id)}/identity-anchor"
            ),
        )

    async def build_reference_set(
        self,
        *,
        bible: CharacterBible,
        style_key: str,
        identity_anchor_url: str,
        data_dir: Path = Path("data/characters"),
    ) -> CharacterReferenceSet:
        if not identity_anchor_url.strip():
            raise ValueError("identity_anchor_url must not be empty")
        style = resolve_style(style_key)
        identity = bible.identity_prompt()

        front = await self._generate_image(
            prompt=(
                f"{identity}\nVisual style: {style}.\n"
                "The supplied image is the shared canonical identity anchor. Render the EXACT SAME character "
                "in the requested visual style while changing only material/rendering language. Preserve the "
                "anchor silhouette, head-to-body ratio, limb lengths, face placement, colors, accessory geometry "
                "and distinguishing feature exactly. Full-body FRONT view, centered neutral standing pose, arms/legs "
                "clearly separated, simple neutral miniature studio background, soft even lighting, vertical 9:16. "
                "This is an identity reference, not a story scene. No text, labels, borders or watermark."
            ),
            references=[identity_anchor_url],
        )
        three_quarter = await self._generate_image(
            prompt=(
                f"{identity}\nVisual style: {style}.\n"
                "The first supplied image is the cross-style identity anchor and the second is this style's canonical "
                "front view. Render the EXACT SAME character in a neutral full-body three-quarter view. Preserve every "
                "locked trait, silhouette, color, accessory, proportions, face and requested material. Same neutral "
                "miniature studio setup and lighting. No text, labels, borders or watermark."
            ),
            references=[identity_anchor_url, front],
        )
        side = await self._generate_image(
            prompt=(
                f"{identity}\nVisual style: {style}.\n"
                "Use the supplied cross-style identity anchor plus this style's front and three-quarter references to "
                "render the EXACT SAME character in a neutral full-body SIDE view. Preserve every locked trait, "
                "silhouette, color, accessory, proportions, face and requested material. Same neutral miniature studio "
                "setup and lighting. No text, labels, borders or watermark."
            ),
            references=[identity_anchor_url, front, three_quarter],
        )

        persisted = await self._persist_reference_urls(
            bible.character_id,
            style_key,
            [front, three_quarter, side],
        )
        result = CharacterReferenceSet(
            character_id=bible.character_id,
            style_key=style_key,
            style_description=style,
            bible=bible,
            identity_anchor_url=identity_anchor_url,
            front_url=persisted[0],
            three_quarter_url=persisted[1],
            side_url=persisted[2],
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._slug(bible.character_id)}-{self._slug(style_key)}.json"
        (data_dir / filename).write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    async def _generate_image(self, *, prompt: str, references: list[str]) -> str:
        return await self.image_provider.generate(
            prompt=prompt,
            references=references,
            size="1K",
            ratio="9:16",
        )

    async def _persist_reference_urls(
        self,
        character_id: str,
        style_key: str,
        urls: list[str],
    ) -> list[str]:
        names = ["front", "three-quarter", "side"]
        saved: list[str] = []
        with tempfile.TemporaryDirectory(prefix="aniflow-character-") as tmp:
            root = Path(tmp)
            for name, url in zip(names, urls, strict=True):
                raw = await download_file(url, root / f"{name}.bin", timeout_seconds=360.0)
                suffix = self._image_suffix(raw)
                local = raw.with_suffix(suffix)
                raw.replace(local)
                object_key = (
                    f"aniflow/characters/{self._slug(character_id)}/"
                    f"{self._slug(style_key)}/{name}{suffix}"
                )
                public = await self.media_store.upload(local, object_key)
                saved.append(public)
        return saved

    @staticmethod
    def _image_suffix(path: Path) -> str:
        header = path.read_bytes()[:16]
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if header.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return ".webp"
        return ".bin"

    @staticmethod
    def _parse_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1).strip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise AgnesApiError("Character bible did not return JSON")
            value = json.loads(cleaned[start : end + 1])
        if not isinstance(value, dict):
            raise AgnesApiError("Character bible JSON root must be an object")
        return value

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
        return slug or "character"
