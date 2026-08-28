from pathlib import Path

import pytest

from aniflow.agnes.key_pool import KeyPool
from aniflow.config import Settings
from aniflow.pipeline.character import CharacterBible, CharacterBuilder


def _bible() -> CharacterBible:
    return CharacterBible(
        character_id="filo",
        display_name="Filo",
        species_or_type="fox",
        body_shape="round body with short limbs",
        proportions="large head, compact body",
        primary_colors=["orange", "white"],
        face_and_eyes="black button eyes, white muzzle",
        accessory="green scarf",
        distinguishing_feature="slightly bent left ear",
        personality_visual_cues=["curious", "gentle"],
        locked_traits=["green scarf", "bent left ear"],
    )


class FakeImageProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return f"https://provider.test/character-{len(self.calls)}.png"


def test_character_identity_prompt_contains_locked_traits():
    prompt = _bible().identity_prompt()
    assert "green scarf" in prompt
    assert "bent left ear" in prompt
    assert "orange" in prompt


def test_image_suffix_detection(tmp_path: Path):
    png = tmp_path / "a.bin"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
    assert CharacterBuilder._image_suffix(png) == ".png"

    jpg = tmp_path / "b.bin"
    jpg.write_bytes(b"\xff\xd8\xff" + b"x" * 16)
    assert CharacterBuilder._image_suffix(jpg) == ".jpg"

    webp = tmp_path / "c.bin"
    webp.write_bytes(b"RIFF1234WEBP" + b"x" * 16)
    assert CharacterBuilder._image_suffix(webp) == ".webp"


@pytest.mark.asyncio
async def test_character_builder_accepts_custom_image_provider():
    provider = FakeImageProvider()
    builder = CharacterBuilder(
        settings=Settings(),
        key_pool=KeyPool(["key-1"]),
        http=object(),
        image_client=None,
        media_store=object(),
        image_provider=provider,
    )

    result = await builder._generate_image(
        prompt="canonical fox identity anchor",
        references=["https://example.test/ref.png"],
    )

    assert result.endswith("character-1.png")
    assert provider.calls == [
        {
            "prompt": "canonical fox identity anchor",
            "references": ["https://example.test/ref.png"],
            "size": "1K",
            "ratio": "9:16",
        }
    ]


@pytest.mark.asyncio
async def test_style_reference_chain_reuses_shared_identity_anchor(monkeypatch, tmp_path: Path):
    builder = CharacterBuilder(
        settings=Settings(),
        key_pool=KeyPool(["key-1"]),
        http=object(),
        image_client=object(),
        media_store=object(),
    )
    calls: list[list[str]] = []

    async def fake_generate_image(*, prompt: str, references: list[str]) -> str:
        calls.append(list(references))
        return f"https://example.test/generated-{len(calls)}.png"

    async def fake_persist(character_id: str, style_key: str, urls: list[str]) -> list[str]:
        assert character_id == "filo"
        assert style_key == "clay"
        return [f"https://media.example/{index}.png" for index, _ in enumerate(urls)]

    monkeypatch.setattr(builder, "_generate_image", fake_generate_image)
    monkeypatch.setattr(builder, "_persist_reference_urls", fake_persist)

    anchor = "https://media.example/identity-anchor.png"
    result = await builder.build_reference_set(
        bible=_bible(),
        style_key="clay",
        identity_anchor_url=anchor,
        data_dir=tmp_path,
    )

    assert result.identity_anchor_url == anchor
    assert calls[0] == [anchor]
    assert calls[1] == [anchor, "https://example.test/generated-1.png"]
    assert calls[2] == [
        anchor,
        "https://example.test/generated-1.png",
        "https://example.test/generated-2.png",
    ]
