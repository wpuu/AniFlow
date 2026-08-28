from aniflow.pipeline.benchmark import BenchmarkRow, BenchmarkRunner


def test_style_summary_aggregates_completed_rows():
    rows = [
        BenchmarkRow(
            style_key="felt",
            idea_index=1,
            episode_id="a",
            title="A",
            premise="A",
            completed=True,
            ab_score=90,
            bc_score=92,
            ab_rounds=1,
            bc_rounds=2,
            final_qa_total=88,
            final_qa_advisory_pass=True,
        ),
        BenchmarkRow(
            style_key="felt",
            idea_index=2,
            episode_id="b",
            title="B",
            premise="B",
            completed=False,
            ab_rounds=3,
            bc_rounds=3,
        ),
    ]
    summary = BenchmarkRunner._summaries(rows, ["felt"])[0]
    assert summary.attempted == 2
    assert summary.completed == 1
    assert summary.completion_rate == 0.5
    assert summary.mean_ab_score == 90
    assert summary.mean_bc_score == 92
    assert summary.mean_rounds == 2.25
    assert summary.mean_final_qa_score == 88
    assert summary.final_qa_advisory_rate == 1.0


def test_calibration_rows_copy_machine_data_and_leave_human_fields_empty():
    rows = [
        BenchmarkRow(
            style_key="clay",
            idea_index=1,
            episode_id="ep-1",
            title="Tiny Umbrella",
            premise="A tiny umbrella opens in the rain",
            completed=True,
            final_public_url="https://example.test/ep-1.mp4",
            ab_score=86,
            bc_score=89,
            final_qa_total=84,
            final_qa_advisory_pass=True,
        )
    ]
    calibration = BenchmarkRunner._calibration_rows(rows)[0]
    assert calibration.episode_id == "ep-1"
    assert calibration.machine_ab_score == 86
    assert calibration.machine_bc_score == 89
    assert calibration.machine_final_qa_score == 84
    assert calibration.machine_final_qa_pass is True
    assert calibration.human_usable is None
    assert calibration.issue_identity is False
    assert calibration.issue_seam is False
