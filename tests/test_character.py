from pathlib import Path

from aniflow.pipeline.character import CharacterBible, CharacterBuilder


def test_character_identity_prompt_contains_locked_traits():
    bible = CharacterBible(
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
    prompt = bible.identity_prompt()
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
