from __future__ import annotations

import asyncio
import json
import statistics
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.agnes.key_pool import KeyPool
from aniflow.config import Settings
from aniflow.media.ffmpeg import extract_sample_frames
from aniflow.media.store import PublicMediaStore
from aniflow.pipeline.keyframes import KeyframeSet
from aniflow.pipeline.storyboard import Storyboard3


class FinalQaScores(BaseModel):
    character_identity: float = Field(ge=0, le=100)
    style_consistency: float = Field(ge=0, le=100)
    seam_continuity: float = Field(ge=0, le=100)
    temporal_integrity: float = Field(ge=0, le=100)
    story_clarity: float = Field(ge=0, le=100)
    pacing: float = Field(ge=0, le=100)
    visual_appeal: float = Field(ge=0, le=100)
    hard_fail: bool = False
    hard_fail_reasons: list[str] = Field(default_factory=list)
    diagnosis: list[str] = Field(default_factory=list)

    @property
    def total(self) -> float:
        weights = {
            "character_identity": 0.20,
            "style_consistency": 0.10,
            "seam_continuity": 0.20,
            "temporal_integrity": 0.15,
            "story_clarity": 0.15,
            "pacing": 0.10,
            "visual_appeal": 0.10,
        }
        return round(sum(getattr(self, key) * weight for key, weight in weights.items()), 2)

    @property
    def advisory_pass(self) -> bool:
        return (
            not self.hard_fail
            and self.total >= 80
            and self.character_identity >= 85
            and self.seam_continuity >= 80
            and self.temporal_integrity >= 80
        )


class EpisodeFinalQa:
    """Advisory QA over the assembled 10-second episode.

    Segment QA remains the hard production gate in V0.1. Final QA is recorded for
    the first benchmark so its thresholds can be calibrated against human ratings.
    """

    FOCI = (
        "character identity and material/style consistency across the whole episode",
        "the A→B / B→C join near the middle, temporal artifacts, jumps, duplicate frames and geometry integrity",
        "whole-story clarity, pacing, readable motion and visual appeal for a silent short video",
    )

    def __init__(
        self,
        *,
        settings: Settings,
        key_pool: KeyPool,
        http: AgnesHttpClient,
        media_store: PublicMediaStore,
    ) -> None:
        self.settings = settings
        self.key_pool = key_pool
        self.http = http
        self.media_store = media_store

    async def evaluate(
        self,
        *,
        episode_id: str,
        final_path: Path,
        storyboard: Storyboard3,
        keyframes: KeyframeSet,
    ) -> FinalQaScores:
        # 49% and 51% deliberately bracket the AB/BC assembly seam.
        fractions = (0.0, 0.2, 0.4, 0.49, 0.51, 0.6, 0.8, 1.0)
        with tempfile.TemporaryDirectory(prefix="aniflow-finalqa-") as tmp:
            frames = await extract_sample_frames(final_path, Path(tmp) / "frames", fractions=fractions)
            keys = [f"aniflow/tmp/final-qa/{episode_id}/{path.name}" for path in frames]
            urls = await asyncio.gather(
                *[self.media_store.upload(path, key) for path, key in zip(frames, keys, strict=True)]
            )
            try:
                results = await asyncio.gather(
                    *[
                        self._judge_once(
                            focus=focus,
                            storyboard=storyboard,
                            keyframes=keyframes,
                            sampled_urls=list(urls),
                        )
                        for focus in self.FOCI
                    ]
                )
            finally:
                await self.media_store.delete_many(keys)

        numeric = (
            "character_identity",
            "style_consistency",
            "seam_continuity",
            "temporal_integrity",
            "story_clarity",
            "pacing",
            "visual_appeal",
        )
        merged = {
            field: float(statistics.median(getattr(item, field) for item in results))
            for field in numeric
        }
        merged["hard_fail"] = any(item.hard_fail for item in results)
        merged["hard_fail_reasons"] = self._unique(
            reason for item in results for reason in item.hard_fail_reasons
        )
        merged["diagnosis"] = self._unique(
            reason for item in results for reason in item.diagnosis
        )
        return FinalQaScores.model_validate(merged)

    async def _judge_once(
        self,
        *,
        focus: str,
        storyboard: Storyboard3,
        keyframes: KeyframeSet,
        sampled_urls: list[str],
    ) -> FinalQaScores:
        slot = await self.key_pool.next()
        prompt = f"""
You are a strict final quality-control judge for one assembled silent vertical animation.
Primary focus: {focus}.

Target story title: {storyboard.title}
Premise: {storyboard.premise}
A→B intended action: {storyboard.action_ab}
B→C intended action: {storyboard.action_bc}

Image order:
1. target keyframe A
2. target keyframe B (the intended assembly seam state)
3. target keyframe C
4+. final assembled-video samples in chronological order. Two samples tightly bracket the middle seam.

Score 0-100 conservatively. Set hard_fail=true for severe identity replacement, severe anatomy/geometry corruption, a clearly broken middle join, frozen/corrupt output, major subject disappearance, or a final episode that no longer communicates the intended story.

Return JSON only:
{{
  "character_identity": 0,
  "style_consistency": 0,
  "seam_continuity": 0,
  "temporal_integrity": 0,
  "story_clarity": 0,
  "pacing": 0,
  "visual_appeal": 0,
  "hard_fail": false,
  "hard_fail_reasons": [],
  "diagnosis": []
}}
""".strip()
        content: list[dict] = [{"type": "text", "text": prompt}]
        for url in [
            keyframes.frame_a_url,
            keyframes.frame_b_url,
            keyframes.frame_c_url,
            *sampled_urls,
        ]:
            content.append({"type": "image_url", "image_url": {"url": url}})

        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/chat/completions",
            api_key=slot.api_key,
            json={
                "model": self.settings.agnes_text_model,
                "messages": [
                    {"role": "system", "content": "Judge the assembled animation strictly. Return JSON only."},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.1,
                "max_tokens": 1400,
            },
        )
        try:
            text = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesApiError("Final QA response missing assistant content") from exc
        return FinalQaScores.model_validate(self._parse_json(text))

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
                raise AgnesApiError("Final QA did not return JSON")
            value = json.loads(cleaned[start : end + 1])
        if not isinstance(value, dict):
            raise AgnesApiError("Final QA JSON root must be an object")
        return value

    @staticmethod
    def _unique(values) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            item = str(value).strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result
