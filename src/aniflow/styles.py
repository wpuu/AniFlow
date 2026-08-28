from __future__ import annotations

STYLE_PRESETS: dict[str, str] = {
    "felt": (
        "handmade needle-felt miniature stop-motion look; visible wool fibers, soft tactile surfaces, "
        "small handcrafted imperfections, warm practical lighting, shallow depth of field, miniature diorama"
    ),
    "clay": (
        "handmade clay stop-motion miniature look; matte sculpted clay, subtle fingerprints, rounded forms, "
        "practical studio lighting, shallow depth of field, handcrafted diorama"
    ),
    "toy": (
        "miniature toy-world cinematic diorama; physical small-scale toy materials, clean stylized shapes, "
        "practical miniature lighting, shallow depth of field, believable handcrafted set"
    ),
}


def resolve_style(value: str) -> str:
    key = value.strip().lower()
    return STYLE_PRESETS.get(key, value.strip())
