from __future__ import annotations

from aniflow.agnes.http import AgnesApiError, AgnesHttpClient
from aniflow.config import Settings
from aniflow.models import JudgeScores


class PromptRepairer:
    def __init__(self, settings: Settings, http: AgnesHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def repair_video_prompt(
        self,
        *,
        api_key: str,
        original_prompt: str,
        story_action: str,
        scores: JudgeScores,
    ) -> str:
        diagnosis = "\n".join(f"- {item}" for item in scores.diagnosis) or "- No diagnosis supplied"
        advice = "\n".join(f"- {item}" for item in scores.repair_advice) or "- No repair advice supplied"
        hard_fail = "\n".join(f"- {item}" for item in scores.hard_fail_reasons) or "- None"
        instruction = f"""
You are repairing a prompt for Agnes Video 2.5 Flash keyframe mode.
The first and last frame are already fixed by the API. Rewrite only the motion/camera/consistency prompt.

Story action:
{story_action}

Original prompt:
{original_prompt}

Hard failures:
{hard_fail}

Diagnosis:
{diagnosis}

Judge advice:
{advice}

Rules:
- Preserve character identity, material, clothing, colors, proportions and background layout.
- Prefer simple controlled motion over complex choreography.
- Explicitly lock anything that should not change.
- Avoid unnecessary camera motion.
- Describe a smooth transition from the first composition to the final composition.
- Do not mention scores, judges or debugging.
- Return only the improved English video prompt, no markdown and no explanation.
""".strip()
        payload = {
            "model": self.settings.agnes_text_model,
            "messages": [{"role": "user", "content": instruction}],
            "temperature": 0.25,
            "max_tokens": 900,
        }
        data = await self.http.request_json(
            "POST",
            f"{self.settings.agnes_v1_url}/chat/completions",
            api_key=api_key,
            json=payload,
        )
        try:
            text = str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AgnesApiError("Prompt repair response missing assistant content") from exc
        if not text:
            raise AgnesApiError("Prompt repair returned empty content")
        return text
