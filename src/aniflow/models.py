from __future__ import annotations

from pydantic import BaseModel, Field


class JudgeScores(BaseModel):
    character_identity: float = Field(ge=0, le=100)
    style_consistency: float = Field(ge=0, le=100)
    anatomy_integrity: float = Field(ge=0, le=100)
    background_continuity: float = Field(ge=0, le=100)
    start_frame_match: float = Field(ge=0, le=100)
    end_frame_match: float = Field(ge=0, le=100)
    motion_quality: float = Field(ge=0, le=100)
    story_accuracy: float = Field(ge=0, le=100)
    visual_appeal: float = Field(ge=0, le=100)
    hard_fail: bool = False
    hard_fail_reasons: list[str] = Field(default_factory=list)
    diagnosis: list[str] = Field(default_factory=list)
    repair_advice: list[str] = Field(default_factory=list)

    def weighted_total(self) -> float:
        weights = {
            "character_identity": 0.20,
            "style_consistency": 0.10,
            "anatomy_integrity": 0.15,
            "background_continuity": 0.10,
            "start_frame_match": 0.075,
            "end_frame_match": 0.075,
            "motion_quality": 0.10,
            "story_accuracy": 0.10,
            "visual_appeal": 0.10,
        }
        return round(sum(getattr(self, key) * weight for key, weight in weights.items()), 2)

    def passes(self, minimum_total: float = 82.0) -> bool:
        if self.hard_fail:
            return False
        if self.character_identity < 88:
            return False
        if self.anatomy_integrity < 85:
            return False
        if min(self.start_frame_match, self.end_frame_match) < 85:
            return False
        return self.weighted_total() >= minimum_total


class VideoTask(BaseModel):
    video_id: str
    status: str | None = None
    raw: dict = Field(default_factory=dict)


class VideoResult(BaseModel):
    video_id: str
    status: str
    video_url: str | None = None
    raw: dict = Field(default_factory=dict)


class CandidateEvaluation(BaseModel):
    candidate_id: str
    video_url: str
    scores: JudgeScores

    @property
    def total(self) -> float:
        return self.scores.weighted_total()
