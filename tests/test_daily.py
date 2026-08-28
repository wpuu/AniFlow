import json
from pathlib import Path

from aniflow.pipeline.daily import DailyHistory, DailyHistoryItem, DailyRunner


def test_missing_daily_history_is_empty(tmp_path: Path):
    history = DailyRunner._load_history(tmp_path / "missing.json")
    assert history.items == []


def test_daily_history_round_trip(tmp_path: Path):
    path = tmp_path / "history.json"
    history = DailyHistory(
        items=[
            DailyHistoryItem(
                episode_id="ep1",
                created_at="2026-08-28T00:00:00+00:00",
                character_id="filo",
                style_key="felt",
                title="Berry Door",
                premise="A fox finds a berry.",
                completed=True,
                final_public_url="https://example.com/ep1.mp4",
                ab_score=90,
                bc_score=91,
                ab_rounds=1,
                bc_rounds=1,
            )
        ]
    )
    path.write_text(json.dumps(history.model_dump()), encoding="utf-8")
    loaded = DailyRunner._load_history(path)
    assert loaded.items[0].title == "Berry Door"
    assert loaded.items[0].completed is True
