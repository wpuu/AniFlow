from types import SimpleNamespace

import pytest

from aniflow.agnes.key_pool import KeyPool
from aniflow.pipeline.keyframes import KeyframeGenerator
from aniflow.pipeline.storyboard import FramePlan, Storyboard3


class FakeImageClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(url=f"https://example.test/frame-{len(self.calls)}.png")


def _storyboard() -> Storyboard3:
    return Storyboard3(
        title="Tiny test",
        premise="A simple visual transition",
        frame_a=FramePlan(
            composition="A",
            character_state="standing",
            environment="tabletop",
            image_prompt="Frame A prompt",
        ),
        frame_b=FramePlan(
            composition="B",
            character_state="moving",
            environment="tabletop",
            image_prompt="Frame B prompt",
        ),
        frame_c=FramePlan(
            composition="C",
            character_state="stopped",
            environment="tabletop",
            image_prompt="Frame C prompt",
        ),
        action_ab="move once",
        action_bc="stop once",
        video_prompt_ab="controlled move",
        video_prompt_bc="controlled stop",
    )


@pytest.mark.asyncio
async def test_selected_style_is_locked_into_all_keyframe_prompts():
    client = FakeImageClient()
    generator = KeyframeGenerator(KeyPool(["key-1"]), client)

    result = await generator.generate_three(
        storyboard=_storyboard(),
        character_reference_urls=["https://example.test/character.png"],
        style="handmade clay stop-motion miniature",
    )

    assert result.frame_a_url.endswith("frame-1.png")
    assert result.frame_b_url.endswith("frame-2.png")
    assert result.frame_c_url.endswith("frame-3.png")
    assert len(client.calls) == 3

    for call in client.calls:
        prompt = call["prompt"]
        assert "handmade clay stop-motion miniature" in prompt
        assert "needle-felt" not in prompt
        assert call["ratio"] == "9:16"
        assert call["size"] == "1K"


def test_empty_style_is_rejected_before_generation():
    client = FakeImageClient()
    generator = KeyframeGenerator(KeyPool(["key-1"]), client)

    with pytest.raises(ValueError, match="Visual style"):
        import asyncio

        asyncio.run(
            generator.generate_three(
                storyboard=_storyboard(),
                character_reference_urls=["https://example.test/character.png"],
                style="   ",
            )
        )
