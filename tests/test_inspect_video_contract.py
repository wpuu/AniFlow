"""Shotlist-locked MP4 acceptance regression cases; no actual provider access."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_video_output.py"
SPEC = importlib.util.spec_from_file_location("inspect_video_output", SCRIPT)
assert SPEC and SPEC.loader
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


def shot(index: int, seconds: int = 5, inherit: bool = False) -> dict:
    value = {"shot_id": str(index), "seconds": seconds, "narration": "测试旁白", "last_frame": {"shape": "ok"}}
    if inherit:
        value["first_frame_from_previous"] = True
    else:
        value["first_frame"] = {"shape": "ok"}
    return value


def sample_shotlist() -> dict:
    return {"episode_id": "MYCL-001", "aspect_ratio": "9:16", "shots": [
        shot(1, 5), shot(2, 5), shot(3, 8), shot(4, 5, True),
        shot(5, 6, True), shot(6, 7), shot(7, 5, True), shot(8, 5, True),
    ]}


def probe_result(seconds: str = "46", audio_seconds: str = "46", audio_start: str = "0") -> dict:
    return {"format": {"duration": seconds}, "streams": [
        {"codec_type": "video", "width": 720, "height": 1280},
        {"codec_type": "audio", "duration": audio_seconds, "start_time": audio_start},
    ]}


class ShotlistAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.shotlist_path = self.root / "MYCL-001.json"
        self.save(sample_shotlist())

    def save(self, data):
        self.shotlist_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_eight_shots_lock_to_exactly_46_seconds(self):
        contract = qa.read_shotlist_contract(self.shotlist_path)
        self.assertEqual(contract["shot_count"], 8)
        self.assertEqual(contract["expected_duration_seconds"], 46)
        self.assertEqual(contract["episode_id"], "MYCL-001")
        self.assertEqual(len(contract["shotlist_sha256"]), 64)

    def test_shotlist_content_change_changes_fingerprint(self):
        old = qa.read_shotlist_contract(self.shotlist_path)["shotlist_sha256"]
        new = sample_shotlist()
        new["shots"][-1]["narration"] = "被修改的结尾"
        self.save(new)
        self.assertNotEqual(old, qa.read_shotlist_contract(self.shotlist_path)["shotlist_sha256"])

    def test_short_episode_blocked_when_range_would_otherwise_accept(self):
        result = qa.inspect_metadata(probe_result(seconds="40", audio_seconds="40"),
                                     min_seconds=30, max_seconds=60, expected_seconds=46,
                                     require_audio=True, require_audio_coverage=True)
        self.assertIn("Final video duration differs from locked shotlist", result["blockers"])

    def test_exact_duration_and_full_audio_coverage(self):
        result = qa.inspect_metadata(probe_result(), min_seconds=30, max_seconds=60,
                                     expected_seconds=46, require_audio=True, require_audio_coverage=True)
        self.assertEqual(result["result"], "METADATA_OK_HUMAN_QA_REQUIRED")
        self.assertEqual(result["audio_duration_seconds"], 46)

    def test_audio_ending_early_is_blocked(self):
        result = qa.inspect_metadata(probe_result(audio_seconds="30"), min_seconds=30,
                                     max_seconds=60, expected_seconds=46, require_audio_coverage=True)
        self.assertIn("Audio stream does not cover the expected episode timeline", result["blockers"])

    def test_audio_starting_late_is_blocked(self):
        result = qa.inspect_metadata(probe_result(audio_start="4", audio_seconds="42"),
                                     min_seconds=30, max_seconds=60, expected_seconds=46, require_audio_coverage=True)
        self.assertIn("Audio stream does not cover the expected episode timeline", result["blockers"])

    def test_missing_audio_stream_metadata_is_blocked(self):
        data = probe_result()
        data["streams"][1].pop("duration")
        result = qa.inspect_metadata(data, min_seconds=30, max_seconds=60, require_audio_coverage=True)
        self.assertIn("Audio stream duration/start metadata missing", result["blockers"])

    def test_unexpected_audio_stream_count_is_blocked(self):
        data = probe_result()
        data["streams"].append(data["streams"][1].copy())
        result = qa.inspect_metadata(data, min_seconds=30, max_seconds=60, require_audio_coverage=True)
        self.assertIn("Expected exactly one audio stream for timeline acceptance", result["blockers"])

    def test_duplicate_shot_id_is_blocked(self):
        data = sample_shotlist()
        data["shots"][-1]["shot_id"] = "1"
        self.save(data)
        with self.assertRaisesRegex(qa.ProbeError, "duplicated"):
            qa.read_shotlist_contract(self.shotlist_path)

    def test_missing_inherited_end_frame_is_blocked(self):
        data = sample_shotlist()
        data["shots"][2].pop("last_frame")
        self.save(data)
        with self.assertRaisesRegex(qa.ProbeError, "no preceding last frame"):
            qa.read_shotlist_contract(self.shotlist_path)

    def test_invalid_shot_length_is_blocked(self):
        data = sample_shotlist()
        data["shots"][2]["seconds"] = 13
        self.save(data)
        with self.assertRaisesRegex(qa.ProbeError, "between 4 and 12"):
            qa.read_shotlist_contract(self.shotlist_path)

    def test_wrong_ratio_is_blocked(self):
        data = sample_shotlist()
        data["aspect_ratio"] = "16:9"
        self.save(data)
        with self.assertRaisesRegex(qa.ProbeError, "not 9:16"):
            qa.read_shotlist_contract(self.shotlist_path)

    def test_non_object_shotlist_is_blocked(self):
        self.save([1, 2, 3])
        with self.assertRaisesRegex(qa.ProbeError, "root must be"):
            qa.read_shotlist_contract(self.shotlist_path)

    def test_malformed_probe_json_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Malformed ffprobe stream"):
            qa.inspect_metadata({"streams": ["bad"]})

    def test_bad_tolerance_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "tolerance"):
            qa.inspect_metadata(probe_result(), duration_tolerance=-1)

    def test_inspect_file_binds_contract_without_exposing_full_path(self):
        movie = self.root / "episode.mp4"
        movie.write_bytes(b"synthetic fixture")
        mock = CompletedProcess(args=[], returncode=0, stdout=json.dumps(probe_result()), stderr="")
        with patch.object(qa.subprocess, "run", return_value=mock):
            result = qa.inspect_file(movie, min_seconds=30, max_seconds=60,
                                     require_audio=False, min_short_side=720,
                                     shotlist=self.shotlist_path)
        self.assertEqual(result["result"], "METADATA_OK_HUMAN_QA_REQUIRED")
        self.assertEqual(result["shotlist_contract"]["expected_duration_seconds"], 46)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_cli_shotlist_for_clip_is_blocked(self):
        movie = self.root / "clip.mp4"
        movie.write_bytes(b"synthetic fixture")
        self.assertEqual(qa.main([str(movie), "--kind", "clip", "--shotlist", str(self.shotlist_path)]), 2)

    def test_malformed_format_fails_closed(self):
        sample = probe_result()
        sample["format"] = []
        with self.assertRaisesRegex(ValueError, "format metadata"):
            qa.inspect_metadata(sample)

    def test_malformed_rotation_entry_blocks(self):
        sample = probe_result()
        sample["streams"][0]["side_data_list"] = ["wrong"]
        result = qa.inspect_metadata(sample, min_seconds=30, max_seconds=60)
        self.assertIn("Malformed rotation metadata entry", result["blockers"])

    def test_boolean_dimensions_are_not_accepted(self):
        sample = probe_result()
        sample["streams"][0]["width"] = True
        result = qa.inspect_metadata(sample, min_seconds=30, max_seconds=60)
        self.assertIn("Invalid video dimensions", result["blockers"])

    def test_oversized_shotlist_is_rejected(self):
        self.shotlist_path.write_text(" " * (1_048_577), encoding="utf-8")
        with self.assertRaisesRegex(qa.ProbeError, "exceeds 1 MiB"):
            qa.read_shotlist_contract(self.shotlist_path)


if __name__ == "__main__":
    unittest.main()
