"""P0-006 real local ffmpeg + fail-closed narration-per-scene tests.

All media generated here are synthetic sine tones/color blocks, not Agnes output.
"""
from __future__ import annotations

import importlib.util
import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/assemble_locked_episode.py'
SPEC = importlib.util.spec_from_file_location('assemble_locked_episode_audio_test', SCRIPT)
assert SPEC and SPEC.loader
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class PerShotAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise unittest.SkipTest('ffmpeg/ffprobe not available for media integration tests')
        cls.container = tempfile.TemporaryDirectory(prefix='aniflow-audio006-')
        cls.root = Path(cls.container.name)
        cls.clips = cls.root / 'clips'
        cls.voices = cls.root / 'voices'
        cls.clips.mkdir()
        cls.voices.mkdir()
        cls.seconds = [5, 5, 8, 5, 6, 7, 5, 5]
        cls.frequencies = [263, 353, 449, 557, 643, 743, 859, 953]
        cls.sp = cls.root / 'shotlist.json'
        cls.fp = cls.root / 'factpack.json'
        shots=[]
        for i,sec in enumerate(cls.seconds,1):
            entry={'shot_id':str(i),'seconds':sec,'narration':f'科学旁白镜头{i}',
                   'last_frame':{'subject_state':f'end{i}'},'motion':f'motion{i}'}
            if i in (4,5,7,8):
                entry['first_frame_from_previous']=True
            else:
                entry['first_frame']={'subject_state':f'first{i}'}
            shots.append(entry)
        cls.sp.write_text(json.dumps({'episode_id':'MYCL-001','aspect_ratio':'9:16','shots':shots},ensure_ascii=False),encoding='utf-8')
        cls.fp.write_text(json.dumps({'episode_id':'MYCL-001','forbidden_claims':['错误的事实']}),encoding='utf-8')
        for i,(sec,freq) in enumerate(zip(cls.seconds,cls.frequencies),1):
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi',
                            '-i',f'color=c=black:s=90x160:r=3:d={sec}',
                            '-c:v','mpeg4','-q:v','6',str(cls.clips/f'scene_{i}.mp4')],check=True,capture_output=True)
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi',
                            '-i',f'sine=frequency={freq}:sample_rate=16000:duration={sec-0.6}',
                            '-c:a','pcm_s16le',str(cls.voices/f'narration_{i}.wav')],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,'container'):
            cls.container.cleanup()

    def kw(self, *, output=None, **other):
        return dict(shotlist=self.sp, factpack=self.fp, clips_dir=self.clips,
                    scene_audio_dir=self.voices, output=output or self.root/'output.mp4',
                    width=90,height=160,fixture_mode=True,fps=3,**other)

    def test_per_shot_plan_readonly_and_hashes(self):
        p = self.root/'unused-plan.mp4'
        plan=app.render(**self.kw(output=p))
        self.assertEqual(plan['result'],'PLAN_ONLY_NO_CHANGES')
        self.assertEqual(plan['narration']['mode'],'per_shot')
        self.assertEqual(len(plan['narration']['shots']),8)
        self.assertEqual(plan['total_seconds'],46)
        self.assertFalse(p.exists())
        self.assertTrue(all(len(row['sha256'])==64 for row in plan['narration']['shots']))

    def test_per_shot_real_render_and_spoken_window_alignment(self):
        target=self.root/'render-test.mp4'
        result=app.render(**self.kw(output=target),execute=True)
        self.assertEqual(result['result'],'ASSEMBLED_MP4_HUMAN_QA_REQUIRED')
        self.assertFalse(result['publish_ready'])
        self.assertTrue(target.is_file())
        meta=app._probe(target)
        self.assertAlmostEqual(float(meta['format']['duration']),46,delta=0.75)
        self.assertEqual(len([s for s in meta['streams'] if s.get('codec_type')=='audio']),1)
        # Check tones at the *correct scene positions*, not just that audio exists.
        elapsed=0
        for seconds,freq in zip(self.seconds,self.frequencies):
            got=subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-ss',str(elapsed+0.5),
                                '-i',str(target),'-t','0.25','-vn','-ac','1','-ar','8000',
                                '-f','s16le','pipe:1'],check=True,capture_output=True)
            raw=got.stdout
            self.assertGreater(len(raw),1000)
            data=struct.unpack('<'+'h'*(len(raw)//2),raw)
            def power(f):
                c=sum(x*math.cos(2*math.pi*f*j/8000) for j,x in enumerate(data))
                s=sum(x*math.sin(2*math.pi*f*j/8000) for j,x in enumerate(data))
                return math.hypot(c,s)
            own=power(freq)
            wrong=max(power(f) for f in self.frequencies if f!=freq)
            self.assertGreater(own,wrong*4, f'tone did not align to scene at {elapsed}s')
            elapsed+=seconds

    def test_two_narration_modes_are_rejected(self):
        with self.assertRaisesRegex(app.AssemblyError,'exactly one narration'):
            app.render(**self.kw(narration=self.voices/'narration_1.wav'))

    def test_missing_narration_source_is_rejected(self):
        with self.assertRaisesRegex(app.AssemblyError,'exactly one narration'):
            app.render(**{k:v for k,v in self.kw().items() if k!='scene_audio_dir'})

    def test_missing_one_voice_blocks(self):
        isolated=self.root/'missing-voice'
        isolated.mkdir(exist_ok=True)
        for i in range(1,8):
            shutil.copyfile(self.voices/f'narration_{i}.wav',isolated/f'narration_{i}.wav')
        with self.assertRaisesRegex(app.AssemblyError,'exactly one narration for shot 8'):
            app.render(**{**self.kw(), 'scene_audio_dir':isolated})

    def test_ambiguous_duplicate_voice_formats_block(self):
        isolated=self.root/'duplicate-voice'
        shutil.copytree(self.voices,isolated)
        shutil.copyfile(self.voices/'narration_1.wav',isolated/'narration_1.mp3')
        with self.assertRaisesRegex(app.AssemblyError,'exactly one narration for shot 1'):
            app.render(**{**self.kw(),'scene_audio_dir':isolated})

    def test_voice_longer_than_window_blocks(self):
        isolated=self.root/'too-long-voice'
        shutil.copytree(self.voices,isolated)
        subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi',
                        '-i','sine=frequency=400:sample_rate=16000:duration=7',
                        '-c:a','pcm_s16le',str(isolated/'narration_1.wav')],check=True,capture_output=True)
        with self.assertRaisesRegex(app.AssemblyError,'exceeds its locked shot window'):
            app.render(**{**self.kw(),'scene_audio_dir':isolated})

    def test_voice_too_short_blocks(self):
        isolated=self.root/'too-short-voice'
        shutil.copytree(self.voices,isolated)
        subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi',
                        '-i','sine=frequency=400:sample_rate=16000:duration=0.2',
                        '-c:a','pcm_s16le',str(isolated/'narration_1.wav')],check=True,capture_output=True)
        with self.assertRaisesRegex(app.AssemblyError,'implausibly short'):
            app.render(**{**self.kw(),'scene_audio_dir':isolated})

    def test_symlink_voice_is_blocked(self):
        isolated=self.root/'symlink-voice'
        shutil.copytree(self.voices,isolated)
        old=isolated/'narration_4.wav'
        old.unlink()
        try:
            old.symlink_to(self.voices/'narration_4.wav')
        except (OSError,NotImplementedError):
            self.skipTest('Filesystem disallows symlink')
        with self.assertRaisesRegex(app.AssemblyError,'regular file'):
            app.render(**{**self.kw(),'scene_audio_dir':isolated})

    def test_existing_output_still_rejected(self):
        output=self.root/'existing-file.mp4'
        output.write_bytes(b'not overwritten')
        with self.assertRaisesRegex(app.AssemblyError,'new .mp4'):
            app.render(**self.kw(output=output),execute=True)
        self.assertEqual(output.read_bytes(),b'not overwritten')


if __name__=='__main__':
    unittest.main()
