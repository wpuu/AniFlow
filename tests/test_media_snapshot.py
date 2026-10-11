"""P0-007: source-identity regression tests. Only fake local media is generated."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assemble_locked_episode.py"
SPEC = importlib.util.spec_from_file_location("aniflow_assemble_snapshot_tests", SCRIPT)
assert SPEC and SPEC.loader
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class ImmutableMediaSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise unittest.SkipTest("Local ffmpeg / ffprobe required")
        cls.media_home = tempfile.TemporaryDirectory(prefix="aniflow-snapshot-fixtures-")
        root = Path(cls.media_home.name)
        cls.template_clip = root / "clip.mp4"
        cls.template_audio = root / "narration.wav"
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "color=c=blue:s=90x160:r=3:d=5",
            "-c:v", "mpeg4", "-q:v", "6", str(cls.template_clip),
        ], check=True, capture_output=True)
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "sine=frequency=450:sample_rate=16000:duration=4.1",
            "-c:a", "pcm_s16le", str(cls.template_audio),
        ], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "media_home"):
            cls.media_home.cleanup()

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="aniflow-snapshot-test-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.clips_dir = self.root / "clips"
        self.clips_dir.mkdir()
        self.scene = self.clips_dir / "scene_1.mp4"
        shutil.copy2(self.template_clip, self.scene)
        self.audio = self.root / "voice.wav"
        shutil.copy2(self.template_audio, self.audio)
        self.fact = self.root / "facts.json"
        self.shotlist = self.root / "shotlist.json"
        self.fact.write_text(json.dumps({"episode_id":"SNAP-001", "forbidden_claims":["禁止语句"]}),encoding="utf-8")
        self.shotlist.write_text(json.dumps({"episode_id":"SNAP-001","aspect_ratio":"9:16","shots":[
            {"shot_id":"1","seconds":5,"narration":"猫的舌头接触水面。",
             "first_frame":{"subject_state":"cat"},"last_frame":{"subject_state":"cat"}}
        ]},ensure_ascii=False),encoding="utf-8")
        self.output = self.root / "assembled.mp4"

    def params(self):
        return dict(shotlist=self.shotlist,factpack=self.fact,clips_dir=self.clips_dir,
                    narration=self.audio,output=self.output,width=90,height=160,
                    fixture_mode=True,fps=3)

    def test_stage_source_returns_identical_snapshot_not_a_hardlink(self):
        copy = self.root / "copy.mp4"
        sha = app._hash_file(self.scene)
        app._stage_source(self.scene, copy, sha)
        self.assertEqual(app._hash_file(copy), sha)
        with self.scene.open("ab") as f:
            f.write(b"MUTATED_AFTER_SNAPSHOT")
        self.assertEqual(app._hash_file(copy), sha)
        self.assertNotEqual(app._hash_file(self.scene), sha)

    def test_snapshot_refuses_preexisting_destination_without_overwrite(self):
        dest = self.root / "existing-snapshot.mp4"
        dest.write_bytes(b"DO_NOT_OVERWRITE")
        with self.assertRaisesRegex(app.AssemblyError,"Could not snapshot"):
            app._stage_source(self.scene, dest, app._hash_file(self.scene))
        self.assertEqual(dest.read_bytes(), b"DO_NOT_OVERWRITE")

    def test_snapshot_rejects_modified_file_after_preflight_and_never_publishes(self):
        original = app._snapshot_inputs
        def mutate_before_staging(report, clips, audio_files, dest, **opts):
            with clips[0].open("ab") as f:
                f.write(b"POST_PREFLIGHT_MUTATION")
            return original(report, clips, audio_files, dest, **opts)
        with patch.object(app, "_snapshot_inputs", side_effect=mutate_before_staging):
            with self.assertRaisesRegex(app.AssemblyError,"changed after preflight"):
                app.render(**self.params(),execute=True)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob("aniflow-local-assemble-*")),[])

    def test_audio_mutation_after_preflight_blocks(self):
        original = app._snapshot_inputs
        def mutate_voice(report, clips, audio_files, dest, **opts):
            with audio_files[0].open("ab") as f:
                f.write(b"CHANGED_AUDIO")
            return original(report, clips, audio_files, dest, **opts)
        with patch.object(app, "_snapshot_inputs", side_effect=mutate_voice):
            with self.assertRaisesRegex(app.AssemblyError,"changed after preflight"):
                app.render(**self.params(),execute=True)
        self.assertFalse(self.output.exists())

    def test_ffmpeg_reads_only_staged_sources_and_reports_verified(self):
        real_run = app.subprocess.run
        video_call_inputs = []
        def intercept(cmd, *args, **kwargs):
            if cmd[0] == "ffmpeg" and "-filter_complex" in cmd:
                video_call_inputs.extend(cmd[i+1] for i,x in enumerate(cmd[:-1]) if x == "-i")
            return real_run(cmd, *args, **kwargs)
        with patch.object(app.subprocess, "run",side_effect=intercept):
            result = app.render(**self.params(),execute=True)
        self.assertTrue(self.output.is_file())
        self.assertEqual(result["result"],"ASSEMBLED_MP4_HUMAN_QA_REQUIRED")
        self.assertTrue(result["input_snapshots_verified"])
        self.assertEqual(result["snapshotted_input_count"],2)
        self.assertEqual(len(video_call_inputs),2)
        for source in video_call_inputs:
            self.assertIn("aniflow-local-assemble-",source)
            self.assertNotEqual(source,str(self.scene))
            self.assertNotEqual(source,str(self.audio))
        self.assertAlmostEqual(float(app._probe(self.output)["format"]["duration"]),5,delta=0.75)

    def test_original_modified_during_render_does_not_change_output_snapshot(self):
        real_run = app.subprocess.run
        seen = False
        def mutate_while_encoding(cmd,*args,**kwargs):
            nonlocal seen
            if cmd[0] == "ffmpeg" and "-filter_complex" in cmd:
                seen = True
                # Simulate a user overwriting an original source while ffmpeg runs.
                self.scene.write_bytes(b"NOT_A_VIDEO_ANY_MORE")
            return real_run(cmd,*args,**kwargs)
        with patch.object(app.subprocess,"run",side_effect=mutate_while_encoding):
            result=app.render(**self.params(),execute=True)
        self.assertTrue(seen)
        self.assertTrue(result["input_snapshots_verified"])
        self.assertTrue(self.output.is_file())
        self.assertAlmostEqual(float(app._probe(self.output)["format"]["duration"]),5,delta=0.75)

    def test_plan_does_not_claim_media_were_snapshotted(self):
        report=app.render(**self.params(),execute=False)
        self.assertEqual(report["result"],"PLAN_ONLY_NO_CHANGES")
        self.assertFalse(report["input_snapshots_verified"])
        self.assertFalse(self.output.exists())

    def test_production_720x1280_render_has_verified_source_snapshots(self):
        # Unlike the tiny geometry fixtures, this checks the actual production
        # 720x1280 acceptance path, still using only synthetic colored video.
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "color=c=green:s=720x1280:r=10:d=5",
            "-c:v", "mpeg4", "-q:v", "10", str(self.scene),
        ], check=True, capture_output=True)
        params = self.params()
        params.update(width=720, height=1280, fps=10, fixture_mode=False)
        report = app.render(**params, execute=True)
        self.assertEqual(report["result"], "ASSEMBLED_MP4_HUMAN_QA_REQUIRED")
        self.assertTrue(report["input_snapshots_verified"])
        self.assertFalse(report["publish_ready"])
        movie = app._probe(self.output)
        stream = next(s for s in movie["streams"] if s.get("codec_type") == "video")
        self.assertEqual((stream["width"], stream["height"]), (720,1280))
        self.assertAlmostEqual(float(movie["format"]["duration"]),5,delta=0.75)

    def test_symlink_swap_blocked_at_snapshot(self):
        if not hasattr(Path, "symlink_to"):
            self.skipTest("No symbolic link support")
        sha=app._hash_file(self.scene)
        link=self.root / "fake.mp4"
        try: link.symlink_to(self.scene)
        except (OSError,NotImplementedError): self.skipTest("File-system symlinks unsupported")
        with self.assertRaisesRegex(app.AssemblyError,"regular file unavailable"):
            app._stage_source(link,self.root/"snapshot.mp4",sha)
        self.assertFalse((self.root/"snapshot.mp4").exists())


if __name__ == "__main__":
    unittest.main()
