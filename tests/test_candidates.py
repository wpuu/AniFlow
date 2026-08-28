import pytest

from aniflow.agnes.key_pool import KeyPool
from aniflow.config import Settings
from aniflow.models import VideoResult, VideoTask
from aniflow.pipeline.candidates import CandidateGenerator


class FakeVideoClient:
    async def create_keyframe_task(self, *, api_key, **kwargs):
        return VideoTask(video_id=f"video-{api_key}", status="queued")

    async def wait_for_result(self, *, api_key, video_id, **kwargs):
        return VideoResult(
            video_id=video_id,
            status="completed",
            video_url=f"https://example.com/{api_key}.mp4",
        )


@pytest.mark.asyncio
async def test_default_draw_uses_every_account_at_least_once():
    settings = Settings(
        agnes_api_keys="k1,k2,k3",
        aniflow_candidates_per_segment=2,
    )
    pool = KeyPool(settings.api_keys)
    generator = CandidateGenerator(settings, pool, FakeVideoClient())
    batch = await generator.generate_segment(
        segment_id="ab",
        prompt="move slowly",
        first_frame_url="https://example.com/a.png",
        last_frame_url="https://example.com/b.png",
    )
    assert len(batch.candidates) == 3
    assert {item.account_label for item in batch.candidates} == {
        "account-1",
        "account-2",
        "account-3",
    }
