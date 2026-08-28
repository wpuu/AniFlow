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
