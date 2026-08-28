from __future__ import annotations

import asyncio
import json
import statistics
from typing import Iterable

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.config import Settings
from aniflow.models import JudgeScores


JUDGE_FOCI = (
    "character identity, material/style consistency, and preservation of the subject",
    "anatomy/geometry integrity, temporal continuity, artifacts, and frame matching",
    "story action, camera quality, motion quality, clarity, and visual appeal",
)


class AgnesVisionJudge:
    def __init__(self, settings: Settings, http: AgnesHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def _single_judge(
        self,
        *,
        api_key: str,
        first_frame_url: str,
        last_frame_url: str,
        sampled_frame_urls: list[str],
        story_action: str,
        focus: str,
    ) -> JudgeScores:
        prompt = f"""
You are a strict animation quality-control judge.
Your primary focus is: {focus}.

Image order:
1. target first keyframe
2. target last keyframe
3+. generated video samples in chronological order

Intended action:
{story_action}

Score every field from 0 to 100. Be conservative. Set hard_fail=true for any severe defect such as extra/missing limbs, severe face/body deformation, subject identity replacement, unexpected subject count, major object disappearance, unreadable generated text, severe clipping, or failure to reach the target final composition.

Return JSON only, with exactly this shape:
{{
  "character_identity": 0,
  "style_consistency": 0,
  "anatomy_integrity": 0,
  "background_continuity": 0,
  "start_frame_match": 0,
  "end_frame_match": 0,
  "motion_quality": 0,
  "story_accuracy": 0,
  "visual_appeal": 0,
  "hard_fail": false,
  "hard_fail_reasons": [],
  "diagnosis": [],
  "repair_advice": []
}}
""".strip()

        content: list[dict] = [{"type": "text", "text": prompt}]
        for url in [first_frame_url, last_frame_url, *sampled_frame_urls]:
            content.append({"type": "image_url", "image_url": {"url": url}})

        payload = {
            "model": self.settings.agnes_text_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Judge visual quality strictly. Return machine-readable JSON only.",
                },
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
            "max_tokens": 1800,
        }
        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/chat/completions",
            api_key=api_key,
            json=payload,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesApiError("Agnes vision response missing choices[0].message.content") from exc
        return JudgeScores.model_validate(self._extract_json(text))

    async def judge_three_passes(
        self,
        *,
        api_key: str,
        first_frame_url: str,
        last_frame_url: str,
        sampled_frame_urls: list[str],
        story_action: str,
    ) -> JudgeScores:
        if not sampled_frame_urls:
            raise ValueError("At least one sampled video frame is required")
        results = await asyncio.gather(
            *[
                self._single_judge(
                    api_key=api_key,
                    first_frame_url=first_frame_url,
                    last_frame_url=last_frame_url,
                    sampled_frame_urls=sampled_frame_urls,
                    story_action=story_action,
                    focus=focus,
                )
                for focus in JUDGE_FOCI
            ]
        )
        numeric_fields = (
            "character_identity",
            "style_consistency",
            "anatomy_integrity",
            "background_continuity",
            "start_frame_match",
            "end_frame_match",
            "motion_quality",
            "story_accuracy",
            "visual_appeal",
        )
        merged = {
            name: float(statistics.median(getattr(result, name) for result in results))
            for name in numeric_fields
        }
        merged["hard_fail"] = any(result.hard_fail for result in results)
        merged["hard_fail_reasons"] = self._unique(
            reason for result in results for reason in result.hard_fail_reasons
        )
        merged["diagnosis"] = self._unique(
            item for result in results for item in result.diagnosis
        )
        merged["repair_advice"] = self._unique(
            item for result in results for item in result.repair_advice
        )
        return JudgeScores.model_validate(merged)

    @staticmethod
    def _extract_json(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise AgnesApiError("Vision judge did not return a JSON object")
            parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, dict):
            raise AgnesApiError("Vision judge JSON root must be an object")
        return parsed

    @staticmethod
    def _unique(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            value = str(item).strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result
