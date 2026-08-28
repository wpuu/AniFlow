from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

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
    aniflow_timezone: str = "Asia/Shanghai"

    # Loopback bridge used by the private browser frontend.
    aniflow_bridge_host: str = "127.0.0.1"
    aniflow_bridge_port: int = 8765
    aniflow_frontend_index: str = "apps/grok-frontend/dist/index.html"

    # Optional CapCut/Seedream browser-automation adapter. The model label is
    # intentionally configurable because CapCut rotates available models.
    # `capcut_seedream_model` is only a default; the frontend may send another
    # exact model label per request without changing .env.
    capcut_seedream_model: str = ""
    capcut_runner_command: str = ""
    capcut_runner_timeout_seconds: float = 300.0

    # S3-compatible temporary/public media storage (Cloudflare R2 recommended).
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""
    s3_public_base_url: str = ""
    s3_region: str = "auto"

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

    @field_validator("aniflow_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("aniflow_bridge_port")
    @classmethod
    def validate_bridge_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("ANIFLOW_BRIDGE_PORT must be between 1 and 65535")
        return value

    @field_validator("capcut_runner_timeout_seconds")
    @classmethod
    def validate_capcut_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("CAPCUT_RUNNER_TIMEOUT_SECONDS must be greater than 0")
        return value

    @property
    def api_keys(self) -> list[str]:
        return [item.strip() for item in self.agnes_api_keys.split(",") if item.strip()]

    @property
    def agnes_v1_url(self) -> str:
        return f"{self.agnes_api_root.rstrip('/')}/v1"

    @property
    def s3_ready(self) -> bool:
        return all(
            [
                self.s3_endpoint_url,
                self.s3_access_key_id,
                self.s3_secret_access_key,
                self.s3_bucket,
                self.s3_public_base_url,
            ]
        )

    @property
    def capcut_runner_ready(self) -> bool:
        return bool(self.capcut_runner_command.strip())

    @property
    def capcut_ready(self) -> bool:
        """Whether CapCut can run without a per-request model override."""
        return bool(self.capcut_runner_ready and self.capcut_seedream_model.strip())

    @property
    def frontend_index_path(self) -> Path:
        return Path(self.aniflow_frontend_index).expanduser().resolve()

    @property
    def frontend_ready(self) -> bool:
        return self.frontend_index_path.is_file()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
