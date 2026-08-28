from __future__ import annotations

import json

from pydantic import BaseModel, Field

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.config import Settings


class StoryIdea(BaseModel):
    title: str
    premise: str
    visual_hook: str


class StoryIdeaBatch(BaseModel):
    ideas: list[StoryIdea] = Field(min_length=1)


class IdeaGenerator:
    def __init__(self, settings: Settings, http: AgnesHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def generate(
        self,
        *,
        api_key: str,
        count: int,
        character_description: str,
        style_description: str,
        previous_titles: list[str] | None = None,
    ) -> StoryIdeaBatch:
        previous = previous_titles or []
        previous_text = "\n".join(f"- {title}" for title in previous[-80:]) or "- None"
        instruction = f"""
Create exactly {count} distinct silent micro-story ideas for 10-second vertical animation.

Fixed character:
{character_description}

Visual style:
{style_description}

Avoid repeating these previous titles/concepts:
{previous_text}

Each story must be globally understandable without dialogue or on-screen text and must work as exactly three keyframes A/B/C with two simple ~5-second transitions. Favor one character, one prop, one clear visual surprise, slow/simple motion, fixed or very slow camera, and a satisfying final visual beat. Avoid fighting, crowds, acrobatics, rapid rotation, complicated hand actions, explosions, or transformations that risk identity drift.

Return JSON only:
{{
  "ideas": [
    {{"title":"","premise":"","visual_hook":""}}
  ]
}}
""".strip()
        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/chat/completions",
            api_key=api_key,
            json={
                "model": self.settings.agnes_text_model,
                "messages": [{"role": "user", "content": instruction}],
                "temperature": 0.85,
                "max_tokens": 3200,
            },
        )
        try:
            text = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesApiError("Idea generator response missing assistant content") from exc
        batch = StoryIdeaBatch.model_validate(self._parse_json(text))
        if len(batch.ideas) != count:
            raise AgnesApiError(
                f"Idea generator returned {len(batch.ideas)} ideas, expected exactly {count}"
            )
        return batch

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
                raise AgnesApiError("Idea generator did not return JSON")
            value = json.loads(cleaned[start : end + 1])
        if not isinstance(value, dict):
            raise AgnesApiError("Idea generator JSON root must be an object")
        return value
