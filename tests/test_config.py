import pytest

from aniflow.config import Settings


def test_default_vertical_video_settings():
    settings = Settings(agnes_api_keys="k1,k2")
    assert settings.api_keys == ["k1", "k2"]
    assert settings.aniflow_aspect_ratio == "9:16"
    assert settings.aniflow_video_seconds == 5


def test_video_seconds_follow_agnes_flash_limits():
    with pytest.raises(ValueError):
        Settings(aniflow_video_seconds=3)
    with pytest.raises(ValueError):
        Settings(aniflow_video_seconds=13)


def test_supported_video_aspect_ratios():
    for ratio in ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]:
        assert Settings(aniflow_aspect_ratio=ratio).aniflow_aspect_ratio == ratio
