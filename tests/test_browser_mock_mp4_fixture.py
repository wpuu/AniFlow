"""Proof that committed synthetic browser test footage is real local MP4.

No Agnes API is contacted. The fixture is 1s blue-only video, never user media.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "MOCK_BLUE_LOCAL_NO_AGNES.mp4"
SHA256 = "2f93bf140de2907eea5286ba28fe6bb2e6950543a4c3af6139598ddde8feeaaa"


def test_browser_mock_blue_video_is_real_and_pinned() -> None:
    assert FIXTURE.is_file()
    video = FIXTURE.read_bytes()
    assert len(video) == 1563
    assert video[4:8] == b"ftyp"
    assert hashlib.sha256(video).hexdigest() == SHA256

    ffprobe = shutil.which("ffprobe")
    assert ffprobe, "CI FFprobe is required for the real MP4 fixture contract"
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(FIXTURE)],
        check=True, capture_output=True, text=True, timeout=20,
    )
    metadata = json.loads(result.stdout)
    assert float(metadata["format"]["duration"]) == 1.0
    assert any(s.get("width") == 64 and s.get("height") == 96
               for s in metadata["streams"])
