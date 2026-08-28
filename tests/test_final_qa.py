from aniflow.pipeline.final_qa import FinalQaScores


def test_final_qa_total_and_advisory_pass():
    scores = FinalQaScores(
        character_identity=92,
        style_consistency=90,
        seam_continuity=88,
        temporal_integrity=87,
        story_clarity=85,
        pacing=83,
        visual_appeal=86,
    )
    assert scores.total >= 80
    assert scores.advisory_pass is True


def test_final_qa_hard_fail_always_rejects_advisory_pass():
    scores = FinalQaScores(
        character_identity=99,
        style_consistency=99,
        seam_continuity=99,
        temporal_integrity=99,
        story_clarity=99,
        pacing=99,
        visual_appeal=99,
        hard_fail=True,
        hard_fail_reasons=["broken middle join"],
    )
    assert scores.advisory_pass is False


def test_final_qa_requires_middle_seam_quality():
    scores = FinalQaScores(
        character_identity=95,
        style_consistency=95,
        seam_continuity=60,
        temporal_integrity=95,
        story_clarity=95,
        pacing=95,
        visual_appeal=95,
    )
    assert scores.total >= 80
    assert scores.advisory_pass is False
