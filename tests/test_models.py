from aniflow.models import JudgeScores


def make_scores(**overrides):
    values = {
        "character_identity": 95,
        "style_consistency": 92,
        "anatomy_integrity": 94,
        "background_continuity": 90,
        "start_frame_match": 93,
        "end_frame_match": 92,
        "motion_quality": 88,
        "story_accuracy": 91,
        "visual_appeal": 90,
    }
    values.update(overrides)
    return JudgeScores(**values)


def test_good_candidate_passes():
    scores = make_scores()
    assert scores.weighted_total() >= 82
    assert scores.passes(82)


def test_hard_fail_always_rejects():
    scores = make_scores(hard_fail=True, hard_fail_reasons=["extra limb"])
    assert not scores.passes(82)


def test_identity_floor_rejects_even_with_high_total():
    scores = make_scores(character_identity=87)
    assert not scores.passes(82)


def test_anatomy_floor_rejects():
    scores = make_scores(anatomy_integrity=84)
    assert not scores.passes(82)


def test_keyframe_match_floor_rejects():
    scores = make_scores(end_frame_match=84)
    assert not scores.passes(82)
