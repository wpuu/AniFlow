"""Pure metadata contract tests for locally generated clips; no network access."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/inspect_video_output.py"
SPEC = importlib.util.spec_from_file_location("inspect_video_output", SCRIPT)
assert SPEC and SPEC.loader
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


def meta(w=720, h=1280, duration="6.3", rotate=None, audio=False):
    video = {"codec_type": "video", "width": w, "height": h}
    if rotate is not None:
        video["side_data_list"] = [{"rotation": rotate}]
    streams = [video]
    if audio:
        streams.append({"codec_type": "audio"})
    return {"streams": streams, "format": {"duration": duration}}


class InspectVideoTests(unittest.TestCase):
    def test_normal_portrait_still_needs_human_review(self):
        result = qa.inspect_metadata(meta())
        self.assertEqual(result["result"], "METADATA_OK_HUMAN_QA_REQUIRED")
        self.assertTrue(result["warnings"])
        self.assertEqual(result["display_dimensions"], [720, 1280])

    def test_unrotated_landscape_is_blocked(self):
        self.assertEqual(qa.inspect_metadata(meta(1280, 720))["result"], "BLOCKED")

    def test_rotation_metadata_can_produce_portrait(self):
        result = qa.inspect_metadata(meta(1280, 720, rotate=90))
        self.assertEqual(result["display_dimensions"], [720, 1280])
        self.assertEqual(result["result"], "METADATA_OK_HUMAN_QA_REQUIRED")

    def test_rotation_can_make_coded_portrait_display_landscape(self):
        result = qa.inspect_metadata(meta(720, 1280, rotate=-90))
        self.assertEqual(result["display_dimensions"], [1280, 720])
        self.assertEqual(result["result"], "BLOCKED")

    def test_missing_duration_blocks(self):
        self.assertEqual(qa.inspect_metadata(meta(duration="N/A"))["result"], "BLOCKED")

    def test_missing_video_blocks(self):
        self.assertIn("Expected exactly one video stream", qa.inspect_metadata({"streams": [], "format": {"duration": 6}})["blockers"])

    def test_overshort_resolution_blocks_if_explicitly_required(self):
        self.assertIn("Short side below specified resolution", qa.inspect_metadata(meta(w=90, h=160), min_short_side=720)["blockers"])

    def test_episode_audio_required(self):
        data = meta(duration="46", audio=False)
        self.assertIn("Audio stream missing", qa.inspect_metadata(data, min_seconds=30, max_seconds=60, require_audio=True)["blockers"])

    def test_episode_audio_present(self):
        result = qa.inspect_metadata(meta(duration="46", audio=True), min_seconds=30, max_seconds=60, require_audio=True)
        self.assertEqual(result["result"], "METADATA_OK_HUMAN_QA_REQUIRED")

    def test_unsupported_rotation_blocks(self):
        self.assertEqual(qa.inspect_metadata(meta(rotate=45))["result"], "BLOCKED")

    def test_non_square_aspect_blocks(self):
        self.assertEqual(qa.inspect_metadata(meta(720, 1200))["result"], "BLOCKED")

    def test_file_path_reporting_omits_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.mp4"
            path.write_bytes(b"not a real video (ffprobe mocked)")
            fake = CompletedProcess(args=[], returncode=0, stdout=json.dumps(meta()), stderr="")
            with patch.object(qa.subprocess, "run", return_value=fake):
                result = qa.inspect_file(path, min_seconds=4, max_seconds=12, require_audio=False, min_short_side=0)
            self.assertEqual(result["filename"], "test.mp4")
            self.assertNotIn(tmp, json.dumps(result))

    def test_probe_failure_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.mp4"
            path.write_bytes(b"fixture")
            fake = CompletedProcess(args=[], returncode=1, stdout="", stderr="private technical detail")
            with patch.object(qa.subprocess, "run", return_value=fake):
                with self.assertRaisesRegex(qa.ProbeError, "could not inspect"):
                    qa.inspect_file(path, min_seconds=4, max_seconds=12, require_audio=False, min_short_side=0)


if __name__ == "__main__":
    unittest.main()
