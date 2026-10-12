"""Offline tests for AniFlow→upstream creative checkpoint contract; no keys/network."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/lock_upstream_creative_checkpoint.py"
spec = importlib.util.spec_from_file_location("lock_upstream_creative_checkpoint", SCRIPT)
assert spec and spec.loader
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)


class CheckpointLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sp = self.root / "shotlist.json"
        self.fp = self.root / "facts.json"
        self.task = self.root / "upstream-task"
        self.task.mkdir()
        self.data = {
            "episode_id": "MYCL-001", "aspect_ratio": "9:16", "style": "needle felt",
            "character": "silver cat in white coat", "shots": [],
        }
        for i, secs in enumerate([5, 5, 8, 5, 6, 7, 5, 5], start=1):
            inherit = i in [4, 5, 7, 8]
            shot = {"shot_id": str(i), "seconds": secs, "narration": f"第{i}镜头猫喝水。",
                    "motion": f"action {i}", "camera": "close-up",
                    "last_frame": {"subject_state": f"end {i}"}}
            if inherit:
                shot["first_frame_from_previous"] = True
            else:
                shot["first_frame"] = {"subject_state": f"start {i}"}
            if i == 2:
                shot["character_override"] = "golden retriever"
            self.data["shots"].append(shot)
        self.facts = {"episode_id": "MYCL-001", "forbidden_claims": ["猫靠吸力喝水"]}
        self.write_sources()
        self.contract = lock.lock_contract(self.sp, self.fp)
        self.valid_checkpoint()

    def write_sources(self):
        self.sp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        self.fp.write_text(json.dumps(self.facts, ensure_ascii=False), encoding="utf-8")

    def valid_checkpoint(self):
        c = self.contract
        self.state = {
            "task_type": "creative", "duration_source": "manual", "scene_count": 8,
            "scene_durations": [5, 5, 8, 5, 6, 7, 5, 5],
            "scenes": [{"index": i, "duration": d} for i, d in enumerate(c["scene_durations"])],
            "manual_config": {"enabled": True, "current_checkpoint": "step_script"},
            "step_video_generation": "pending", "step_audio": "pending",
            "narrations": [c["locked_narration"]],
        }
        self.write_task()

    def write_task(self):
        (self.task / "task_state.json").write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        (self.task / "script.json").write_text(json.dumps(self.contract["scene_prompts"], ensure_ascii=False), encoding="utf-8")

    def inspect(self):
        return lock.inspect_checkpoint(self.contract, self.task)

    def test_original_episode_expected_8_shots_46_seconds(self):
        self.assertEqual(self.contract["scene_count"], 8)
        self.assertEqual(self.contract["scene_durations"], [5,5,8,5,6,7,5,5])
        self.assertEqual(self.contract["expected_seconds"], 46)
        self.assertIn("golden retriever", self.contract["scene_prompts"][1])
        self.assertNotIn("silver cat", self.contract["scene_prompts"][1])
        self.assertEqual(self.contract["form_fields"]["execution_mode"], "manual")

    def test_no_task_files_modified_during_validation(self):
        before = {n:(self.task/n).read_bytes() for n in ("task_state.json", "script.json")}
        self.assertEqual(self.inspect()["result"], "CHECKPOINT_TEXT_MATCH_ONLY_HUMAN_REVIEW_REQUIRED")
        after = {n:(self.task/n).read_bytes() for n in before}
        self.assertEqual(before, after)
        self.assertFalse(self.inspect()["safe_to_resume_without_manual_approval"])

    def test_changed_narration_is_blocked_without_leaking_it(self):
        self.state["narrations"][0] = "未经验证的虚假内容123秘密"
        self.write_task()
        result = self.inspect()
        self.assertEqual(result["result"], "BLOCKED")
        self.assertTrue(any("narration" in t for t in result["blockers"]))
        self.assertNotIn("秘密", str(result))

    def test_whitespace_newline_differences_do_not_force_false_failure(self):
        self.state["narrations"][0] = self.contract["locked_narration"].replace("。", "。\n")
        self.write_task()
        self.assertEqual(self.inspect()["result"], "CHECKPOINT_TEXT_MATCH_ONLY_HUMAN_REVIEW_REQUIRED")

    def test_script_auto_rewrite_is_blocked(self):
        (self.task / "script.json").write_text('["not the locked script"]', encoding="utf-8")
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_altered_scene_duration_is_blocked(self):
        self.state["scenes"][0]["duration"] = 9
        self.write_task()
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_wrong_scene_durations_config_blocked(self):
        self.state["scene_durations"] = [10]*8
        self.write_task()
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_audio_started_is_blocked(self):
        self.state["step_audio"] = "completed"
        self.write_task()
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_video_submitted_is_blocked(self):
        self.state["step_video_generation"] = "running"
        self.write_task()
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_wrong_checkpoint_is_blocked(self):
        self.state["manual_config"]["current_checkpoint"] = "step_audio"
        self.write_task()
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_automatic_mode_is_blocked(self):
        self.state["manual_config"]["enabled"] = False
        self.write_task()
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_upstream_task_not_creative_is_blocked(self):
        self.state["task_type"] = "manuscript"
        self.write_task()
        self.assertEqual(self.inspect()["result"], "BLOCKED")

    def test_foreign_factpack_is_blocked(self):
        self.facts["episode_id"] = "OTHER"
        self.write_sources()
        with self.assertRaisesRegex(lock.ContractError, "mismatch"):
            lock.lock_contract(self.sp, self.fp)

    def test_forbidden_claim_in_locked_script_is_blocked(self):
        self.data["shots"][1]["narration"] = "猫靠吸力喝水"
        self.write_sources()
        with self.assertRaisesRegex(lock.ContractError, "forbidden"):
            lock.lock_contract(self.sp, self.fp)

    def test_inherited_frame_missing_is_blocked(self):
        self.data["shots"][2].pop("last_frame")
        self.write_sources()
        with self.assertRaisesRegex(lock.ContractError, "inheritance"):
            lock.lock_contract(self.sp, self.fp)

    def test_bool_duration_is_blocked(self):
        self.data["shots"][0]["seconds"] = True
        self.write_sources()
        with self.assertRaisesRegex(lock.ContractError, "integer"):
            lock.lock_contract(self.sp, self.fp)

    def test_preparation_writes_only_four_isolated_files(self):
        out=self.root/"dryrun"
        x=lock.prepare(self.contract, out)
        self.assertEqual(x["result"], "OFFLINE_EXPORT_CREATED_NOT_IMPORTED")
        self.assertEqual(sorted(x["files"]),sorted(f.name for f in out.iterdir()))
        self.assertEqual(json.loads((out/"script.json").read_text()),self.contract["scene_prompts"])
        self.assertFalse(x["upstream_task_modified"])
        with self.assertRaisesRegex(lock.ContractError, "refusing overwrite"):
            lock.prepare(self.contract,out)

    def test_oversized_state_json_blocks(self):
        (self.task/"task_state.json").write_text(" " * (lock.MAX_JSON+1))
        with self.assertRaisesRegex(lock.ContractError, "larger than"):
            self.inspect()

    def test_missing_script_file_blocks(self):
        (self.task/"script.json").unlink()
        with self.assertRaisesRegex(lock.ContractError, "missing"):
            self.inspect()

    def test_never_reads_env_secret(self):
        secret = self.task/".env"
        secret.write_text("AGNES_API_KEY=DO_NOT_SHOW_ME")
        res=self.inspect()
        self.assertNotIn("DO_NOT_SHOW_ME",str(res))
        self.assertEqual(secret.read_text(),"AGNES_API_KEY=DO_NOT_SHOW_ME")

    def test_prepare_plan_never_creates_files(self):
        dest=self.root/"unused"
        self.assertEqual(lock.main(["--shotlist",str(self.sp),"--factpack",str(self.fp)]),0)
        self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
