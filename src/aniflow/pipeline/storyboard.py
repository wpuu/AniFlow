from __future__ import annotations

import json

from pydantic import BaseModel, Field

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.config import Settings


class FramePlan(BaseModel):
    composition: str
    character_state: str
    environment: str
    image_prompt: str


class Storyboard3(BaseModel):
    title: str
    premise: str
    frame_a: FramePlan
    frame_b: FramePlan
    frame_c: FramePlan
    action_ab: str
    action_bc: str
    video_prompt_ab: str
    video_prompt_bc: str


class StoryboardPlanner:
    def __init__(self, settings: Settings, http: AgnesHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def create_three_frame_storyboard(
        self,
        *,
        api_key: str,
        idea: str,
        character_description: str,
        style: str = "handmade needle-felt miniature animation",
    ) -> Storyboard3:
        instruction = f"""
Design one globally understandable 10-second silent micro-story for vertical short video.

Idea:
{idea}

Fixed character:
{character_description}

Visual style:
{style}

The story MUST use exactly three visual keyframes A, B, C and two ~5-second transitions A→B and B→C.
Optimize for AI keyframe animation reliability:
- one clear main action per transition
- slow/simple controlled motion
- no fighting, acrobatics, fast spinning, complex hand choreography, crowds, or rapid camera cuts
- preserve character identity, clothes/accessories, materials, colors, proportions and environment
- prefer fixed or very slow camera movement
- no dialogue and no required on-screen text
- each frame must have a strong, readable composition in 9:16
- B must work simultaneously as the ending composition of A→B and the starting composition of B→C

For image_prompt, describe subject, scene, felt/material details, lighting, camera/composition, and exactly what must stay unchanged.
For video_prompt_ab/video_prompt_bc, describe only the controlled motion between the already-fixed keyframes, camera behavior, and consistency locks.

Return JSON only with exactly this structure:
{{
  "title": "",
  "premise": "",
  "frame_a": {{"composition":"","character_state":"","environment":"","image_prompt":""}},
  "frame_b": {{"composition":"","character_state":"","environment":"","image_prompt":""}},
  "frame_c": {{"composition":"","character_state":"","environment":"","image_prompt":""}},
  "action_ab": "",
  "action_bc": "",
  "video_prompt_ab": "",
  "video_prompt_bc": ""
}}
""".strip()
        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/chat/completions",
            api_key=api_key,
            json={
                "model": self.settings.agnes_text_model,
                "messages": [{"role": "user", "content": instruction}],
                "temperature": 0.65,
                "max_tokens": 3000,
            },
        )
        try:
            text = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesApiError("Storyboard response missing assistant content") from exc
        return Storyboard3.model_validate(self._parse_json(text))

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
                raise AgnesApiError("Storyboard model did not return JSON")
            value = json.loads(cleaned[start : end + 1])
        if not isinstance(value, dict):
            raise AgnesApiError("Storyboard JSON root must be an object")
        return value
