from __future__ import annotations

from dataclasses import dataclass, field

from aniflow.agnes.key_pool import KeyPool
from aniflow.config import Settings
from aniflow.models import CandidateEvaluation
from aniflow.pipeline.candidates import CandidateGenerator
from aniflow.pipeline.evaluate import CandidateEvaluator
from aniflow.pipeline.repair import PromptRepairer


@dataclass(slots=True)
class RoundSummary:
    round_number: int
    prompt: str
    evaluations: list[CandidateEvaluation] = field(default_factory=list)
    generation_failures: list[str] = field(default_factory=list)
    evaluation_failures: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SegmentRunResult:
    segment_id: str
    selected: CandidateEvaluation | None
    rounds: list[RoundSummary]

    def as_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "selected": self.selected.model_dump() | {"total": self.selected.total}
            if self.selected
            else None,
            "rounds": [
                {
                    "round_number": item.round_number,
                    "prompt": item.prompt,
                    "evaluations": [
                        evaluation.model_dump() | {"total": evaluation.total}
                        for evaluation in item.evaluations
                    ],
                    "generation_failures": item.generation_failures,
                    "evaluation_failures": item.evaluation_failures,
                }
                for item in self.rounds
            ],
        }


class SegmentPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        key_pool: KeyPool,
        generator: CandidateGenerator,
        evaluator: CandidateEvaluator,
        repairer: PromptRepairer,
    ) -> None:
        self.settings = settings
        self.key_pool = key_pool
        self.generator = generator
        self.evaluator = evaluator
        self.repairer = repairer

    async def run(
        self,
        *,
        segment_id: str,
        prompt: str,
        story_action: str,
        first_frame_url: str,
        last_frame_url: str,
        candidates_per_round: int | None = None,
    ) -> SegmentRunResult:
        current_prompt = prompt
        rounds: list[RoundSummary] = []
        total_rounds = self.settings.aniflow_max_repair_rounds + 1

        for round_index in range(total_rounds):
            round_number = round_index + 1
            batch = await self.generator.generate_segment(
                segment_id=f"{segment_id}-r{round_number}",
                prompt=current_prompt,
                first_frame_url=first_frame_url,
                last_frame_url=last_frame_url,
                count=candidates_per_round,
            )
            evaluations, evaluation_failures = await self.evaluator.evaluate_batch(
                job_id=segment_id,
                candidates=batch.candidates,
                first_frame_url=first_frame_url,
                last_frame_url=last_frame_url,
                story_action=story_action,
            )
            summary = RoundSummary(
                round_number=round_number,
                prompt=current_prompt,
                evaluations=evaluations,
                generation_failures=batch.failures,
                evaluation_failures=evaluation_failures,
            )
            rounds.append(summary)

            passing = [
                item for item in evaluations if item.scores.passes(self.settings.aniflow_pass_score)
            ]
            if passing:
                passing.sort(key=lambda item: item.total, reverse=True)
                return SegmentRunResult(segment_id=segment_id, selected=passing[0], rounds=rounds)

            if round_number >= total_rounds:
                break
            if not evaluations:
                # No visual diagnosis is available, so retry the same prompt next round.
                continue

            best_failed = evaluations[0]
            slot = await self.key_pool.next()
            current_prompt = await self.repairer.repair_video_prompt(
                api_key=slot.api_key,
                original_prompt=current_prompt,
                story_action=story_action,
                scores=best_failed.scores,
            )

        return SegmentRunResult(segment_id=segment_id, selected=None, rounds=rounds)
