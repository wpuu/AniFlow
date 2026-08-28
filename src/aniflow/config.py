from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AniFlow runtime settings.

    Real API keys must only come from environment variables or secret stores.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    agnes_api_root: str = "https://apihub.agnes-ai.com"
    agnes_api_keys: str = Field(default="")
    agnes_text_model: str = "agnes-2.5-flash"
    agnes_image_model: str = "agnes-image-2.1-flash"
    agnes_video_model: str = "agnes-video-2.5-flash"

    aniflow_aspect_ratio: str = "9:16"
    aniflow_image_size: str = "1K"
    aniflow_video_seconds: int = 5
    aniflow_candidates_per_segment: int = 5
    aniflow_max_repair_rounds: int = 2
    aniflow_pass_score: float = 82.0
    aniflow_public_media_base_url: str = ""

    @field_validator("aniflow_video_seconds")
    @classmethod
    def validate_video_seconds(cls, value: int) -> int:
        if value < 4 or value > 12:
            raise ValueError("ANIFLOW_VIDEO_SECONDS must be between 4 and 12")
        return value

    @field_validator("aniflow_aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, value: str) -> str:
        allowed = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
        if value not in allowed:
            raise ValueError(f"Unsupported aspect ratio: {value}")
        return value

    @property
    def api_keys(self) -> list[str]:
        return [item.strip() for item in self.agnes_api_keys.split(",") if item.strip()]

    @property
    def agnes_v1_url(self) -> str:
        return f"{self.agnes_api_root.rstrip('/')}/v1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
