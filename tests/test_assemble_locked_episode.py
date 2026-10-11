"""Local-only contract tests. The single ffmpeg integration uses fake colored clips."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assemble_locked_episode.py"
spec = importlib.util.spec_from_file_location("assemble_locked_episode", SCRIPT)
assert spec and spec.loader
assembly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembly)


class LockedAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clips = self.root / "clips"
        self.clips.mkdir()
        self.sp = self.root / "shotlist.json"
        self.fp = self.root / "factpack.json"
        self.audio = self.root / "voice.wav"
        self.output = self.root / "final.mp4"
        self.seconds = [5, 5, 8, 5, 6, 7, 5, 5]
        self.source = {
            "episode_id": "MYCL-001", "aspect_ratio": "9:16", "shots": []
        }
        for i, dur in enumerate(self.seconds, start=1):
            item = {"shot_id": str(i), "seconds": dur, "narration": f"这是真实已校验的第{i}段旁白。",
                    "last_frame": {"description": "x"}}
            if i in (4, 5, 7, 8):
                item["first_frame_from_previous"] = True
            else:
                item["first_frame"] = {"description": "x"}
            self.source["shots"].append(item)
        self.facts = {"episode_id": "MYCL-001", "forbidden_claims": ["吸力喝水"]}
        self.flush()

    def flush(self):
        self.sp.write_text(json.dumps(self.source, ensure_ascii=False), encoding="utf-8")
        self.fp.write_text(json.dumps(self.facts, ensure_ascii=False), encoding="utf-8")

    def build_media(self, *, missing: str | None = None, broken: str | None = None, audio_seconds=31):
        # Very small non-commercial sample, not a provider output.
        colors = ["red", "blue", "green", "white", "orange", "yellow", "purple", "black"]
        for i, sec in enumerate(self.seconds, start=1):
            if missing == str(i):
                continue
            dur = sec - 1 if broken == str(i) else sec
            subprocess.run([
                "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
                "-i", f"color=c={colors[i-1]}:s=90x160:r=3:d={dur}",
                "-t", str(dur), "-c:v", "mpeg4", "-q:v", "5",
                str(self.clips / f"scene_{i}.mp4")
            ], check=True, capture_output=True)
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=440:sample_rate=16000:duration={audio_seconds}",
            "-c:a", "pcm_s16le", str(self.audio)
        ], check=True, capture_output=True)

    def kwargs(self):
        return dict(shotlist=self.sp, factpack=self.fp, clips_dir=self.clips,
                    narration=self.audio, output=self.output, width=90, height=160,
                    fixture_mode=True, fps=3)

    def test_real_myclarity_8_shots_46_seconds(self):
        c=assembly._content_contract(self.sp,self.fp)
        self.assertEqual((c["shot_count"],c["total_seconds"]),(8,46))
        self.assertEqual([x["seconds"] for x in c["schedule"]],self.seconds)
        self.assertEqual(c["schedule"][3]["filename"],"scene_4.mp4")

    def test_ban_dangerous_shot_ids(self):
        self.source["shots"][0]["shot_id"] = "../../secrets"
        self.flush()
        with self.assertRaisesRegex(assembly.AssemblyError,"Invalid or duplicate shot ID"):
            assembly._content_contract(self.sp,self.fp)

    def test_duplicate_shot_id(self):
        self.source["shots"][-1]["shot_id"] = "1"
        self.flush()
        with self.assertRaises(assembly.AssemblyError):
            assembly._content_contract(self.sp,self.fp)

    def test_missing_frame_chain(self):
        self.source["shots"][2].pop("last_frame")
        self.flush()
        with self.assertRaisesRegex(assembly.AssemblyError,"inherited frame"):
            assembly._content_contract(self.sp,self.fp)

    def test_invalid_duration_and_bool(self):
        self.source["shots"][3]["seconds"]=True
        self.flush()
        with self.assertRaisesRegex(assembly.AssemblyError,"Shot duration"):
            assembly._content_contract(self.sp,self.fp)

    def test_forbidden_narration(self):
        self.source["shots"][0]["narration"]="猫靠吸力喝水"
        self.flush()
        with self.assertRaisesRegex(assembly.AssemblyError,"forbidden"):
            assembly._content_contract(self.sp,self.fp)

    def test_wrong_factpack_id(self):
        self.facts["episode_id"]="OTHER"
        self.flush()
        with self.assertRaisesRegex(assembly.AssemblyError,"Episode ID"):
            assembly._content_contract(self.sp,self.fp)

    def test_real_plan_does_not_create_output(self):
        self.build_media()
        plan=assembly.render(**self.kwargs())
        self.assertEqual(plan["result"],"PLAN_ONLY_NO_CHANGES")
        self.assertEqual(plan["shot_count"],8)
        self.assertEqual(plan["total_seconds"],46)
        self.assertFalse(self.output.exists())
        self.assertTrue(plan["narration"]["will_pad_with_silence"])

    def test_real_render_fixed_timeline(self):
        self.build_media()
        report=assembly.render(**self.kwargs(),execute=True)
        self.assertEqual(report["result"],"ASSEMBLED_MP4_HUMAN_QA_REQUIRED")
        self.assertFalse(report["publish_ready"])
        self.assertTrue(self.output.exists())
        meta=assembly._probe(self.output)
        dur=float(meta["format"]["duration"])
        self.assertAlmostEqual(dur,46,delta=0.75)
        self.assertEqual(len([x for x in meta["streams"] if x.get("codec_type")=="audio"]),1)
        self.assertEqual(len(report["output_sha256"]),64)

    def test_missing_scene_blocks(self):
        self.build_media(missing="4")
        with self.assertRaises(assembly.AssemblyError):
            assembly.render(**self.kwargs())
        self.assertFalse(self.output.exists())

    def test_short_scene_blocks(self):
        self.build_media(broken="3")
        with self.assertRaisesRegex(assembly.AssemblyError,"Clip duration"):
            assembly.render(**self.kwargs())

    def test_wrong_geometry_blocks(self):
        self.build_media()
        with self.assertRaisesRegex(assembly.AssemblyError,"Production output must"):
            assembly.render(**(self.kwargs()|{"fixture_mode":False}))

    def test_too_short_narration_blocks(self):
        self.build_media(audio_seconds=2)
        with self.assertRaisesRegex(assembly.AssemblyError,"Narration unexpectedly short"):
            assembly.render(**self.kwargs())

    def test_output_never_overwrites(self):
        self.build_media()
        self.output.write_bytes(b"PREEXISTING_USER_DATA")
        with self.assertRaisesRegex(assembly.AssemblyError,"Output must be a new"):
            assembly.render(**self.kwargs(),execute=True)
        self.assertEqual(self.output.read_bytes(),b"PREEXISTING_USER_DATA")

    def test_symlink_clip_blocks(self):
        self.build_media()
        old=self.clips/"scene_4.mp4"
        old.unlink()
        old.symlink_to(self.clips/"scene_3.mp4")
        with self.assertRaisesRegex(assembly.AssemblyError,"regular file"):
            assembly.render(**self.kwargs())

    def test_nonfinite_tolerance_blocks(self):
        with self.assertRaisesRegex(assembly.AssemblyError,"tolerance"):
            assembly.preflight(**{k:v for k,v in self.kwargs().items() if k!="fps"},tolerance=float('nan'))


if __name__ == "__main__":
    unittest.main()
