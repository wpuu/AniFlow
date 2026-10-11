"""P0-010: no-key network-mocked proof of one submission / durable resume.

The first shot source is the actual repository MYCL-001 JSON. All API replies
and the fake downloaded bytes are generated locally by httpx.MockTransport.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("one_agnes_real_shot", SCRIPTS / "one_agnes_real_shot.py")
assert SPEC and SPEC.loader
shot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shot)


@pytest.fixture
def planned():
    return shot.prepare_plan(
        ROOT / "content/shotlists/MYCL-001-cat-lapping.json",
        ROOT / "content/factpacks/MYCL-001-cat-lapping.json",
    )


@pytest.fixture
def fake_inspection(monkeypatch):
    monkeypatch.setattr(shot.shutil, "which", lambda _: "/tmp/ffprobe")
    monkeypatch.setattr(shot, "_inspect_clip", lambda _: {
        "result": "METADATA_OK_HUMAN_QA_REQUIRED", "blockers": []
    })


def _headers(request: httpx.Request):
    return {k.lower(): v for k, v in request.headers.items()}


def test_exact_audited_first_shot_and_contract_fingerprint(planned):
    assert planned["episode_id"] == "MYCL-001"
    assert planned["shot_id"] == "1"
    assert planned["seconds"] == 5
    assert planned["_request"]["mode"] == "text"
    assert planned["_request"]["model"] == "agnes-video-2.5-flash"
    assert planned["_request"]["seconds"] == "5"
    assert planned["_request"]["size"] == "720P"
    assert planned["_request"]["n"] == 1
    assert planned["_request"]["aspect_ratio"] == "9:16"
    assert "first_frame" not in planned["_request"]
    assert "images" not in planned["_request"]
    assert len(planned["shotlist_sha256"]) == 64
    assert "needle-felt" in planned["_request"]["prompt"]


def test_default_plan_without_key_or_network(planned, tmp_path):
    out = tmp_path / "should-not-exist"
    result = shot.run_live(planned, out, execute=False, resume=False, confirmed_price=False,
                           environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "fake"})
    assert result["result"] == "PLAN_ONLY_NO_REQUESTS"
    assert result["submissions"] == 0
    assert "_request" not in result
    assert not out.exists()


def test_no_explicit_cost_review_blocks_before_any_file_or_network(planned, tmp_path):
    out = tmp_path / "no-consent"
    with pytest.raises(shot.ShotError, match="Review current Agnes billing"):
        shot.run_live(planned, out, execute=True, resume=False, confirmed_price=False,
                      environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "TEST_KEY"})
    assert not out.exists()


def test_missing_or_multi_key_blocks(planned, tmp_path):
    for env in [{}, {"ANIFLOW_SINGLE_SHOT_API_KEY": "a,b"},
                {"ANIFLOW_SINGLE_SHOT_API_KEY": ""}]:
        with pytest.raises(shot.ShotError, match="Exactly one"):
            shot.run_live(planned, tmp_path / "blocked", execute=True, resume=False,
                          confirmed_price=True, environ=env)
    assert not (tmp_path / "blocked").exists()


def test_bad_domain_rejected_before_api_call():
    with pytest.raises(shot.ShotError, match="Unknown Agnes API domain"):
        shot.prepare_plan(ROOT / "content/shotlists/MYCL-001-cat-lapping.json",
                          ROOT / "content/factpacks/MYCL-001-cat-lapping.json",
                          domain="untrusted-server")


def test_explicit_rejected_response_single_post_no_retry(planned, tmp_path, fake_inspection):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.host == "apihub.agnes-ai.com"
        return httpx.Response(503, json={"code": "video_queue_full",
                                         "message": "do not echo private upstream diagnostic"})
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        result = shot.run_live(planned, tmp_path / "rejected", execute=True, resume=False,
                               confirmed_price=True, environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "SECRET_VALUE"},
                               client=client, max_polls=1, sleep_fn=lambda _: None)
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert result["result"] == "REJECTED_NO_VIDEO_ID"
    assert result["submissions"] == 1
    assert result["error_code"] == "video_queue_full"
    record = (tmp_path / "rejected/MYCL-001-shot-1.attempt.json").read_text()
    assert "SECRET_VALUE" not in record
    assert "private upstream diagnostic" not in record
    assert not list((tmp_path / "rejected").glob("*.mp4"))


def test_network_timeout_is_ambiguous_not_resubmitted(planned, tmp_path, fake_inspection):
    count = 0
    def handler(_):
        nonlocal count
        count += 1
        raise httpx.ReadTimeout("could have already accepted submission")
    with (
        httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client,
        pytest.raises(shot.ShotError, match="SUBMISSION_AMBIGUOUS"),
    ):
        shot.run_live(planned, tmp_path / "unknown", execute=True, resume=False,
                      confirmed_price=True, environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "ONE_KEY"},
                      client=client)
    assert count == 1
    data = json.loads((tmp_path / "unknown/MYCL-001-shot-1.attempt.json").read_text())
    assert data["status"] == "SUBMISSION_ATTEMPT_UNCONFIRMED"
    assert data["video_id"] is None


def test_success_download_and_no_key_or_signed_url_leak(planned, tmp_path, fake_inspection):
    events = []
    body = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048
    def handler(request):
        events.append((request.method, str(request.url), _headers(request)))
        if request.method == "POST":
            return httpx.Response(200, json={"video_id": "video_001"})
        if request.url.path == "/agnesapi":
            return httpx.Response(200, json={"status": "completed",
                              "url": "https://cdn.agnes-ai.com/clip.mp4?secret-download-token=PRIVATE"})
        return httpx.Response(200, headers={"Content-Type": "video/mp4"}, content=body)
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        result = shot.run_live(planned, tmp_path / "success", execute=True, resume=False,
                               confirmed_price=True,
                               environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "THIS_KEY_STAYS_LOCAL"},
                               client=client, max_polls=2, poll_interval=0,
                               sleep_fn=lambda _: None)
    assert result["result"] == "MEDIA_REQUIRES_HUMAN_REVIEW"
    assert result["submissions"] == 1
    assert result["pixel_orientation_verified"] is False
    assert result["manual_viewing_required"] is True
    assert [(x[0], x[1].split("?")[0]) for x in events] == [
        ("POST", "https://apihub.agnes-ai.com/v1/videos"),
        ("GET", "https://apihub.agnes-ai.com/agnesapi"),
        ("GET", "https://cdn.agnes-ai.com/clip.mp4"),
    ]
    assert events[0][2]["authorization"] == "Bearer THIS_KEY_STAYS_LOCAL"
    assert events[1][2]["authorization"] == "Bearer THIS_KEY_STAYS_LOCAL"
    assert "authorization" not in events[2][2]
    assert (tmp_path / "success/MYCL-001-shot-1.mp4").read_bytes() == body
    record = (tmp_path / "success/MYCL-001-shot-1.attempt.json").read_text()
    assert "THIS_KEY_STAYS_LOCAL" not in record
    assert "secret-download-token" not in record
    assert hashlib.sha256(body).hexdigest() == result["mp4_sha256"]


def test_existing_output_dir_refuses_second_post(planned, tmp_path, fake_inspection):
    out = tmp_path / "existing"
    out.mkdir()
    touched = []
    def handler(request):
        touched.append(request)
        return httpx.Response(200, json={"video_id": "new_bad"})
    with (
        httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client,
        pytest.raises(shot.ShotError, match="already exists"),
    ):
        shot.run_live(planned, out, execute=True, resume=False,
                      confirmed_price=True, environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "KEY"},
                      client=client)
    assert touched == []


def test_resume_never_posts_and_does_not_overwrite(planned, tmp_path, fake_inspection):
    count = {"POST": 0, "GET": 0}
    def handler(request):
        count[request.method] += 1
        if request.method == "POST":
            return httpx.Response(200, json={"video_id": "resume_123"})
        return httpx.Response(200, json={"status": "processing"})
    out = tmp_path / "resume"
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        pending = shot.run_live(planned, out, execute=True, resume=False,
                                confirmed_price=True, environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "K"},
                                client=client, max_polls=1, sleep_fn=lambda _: None)
        restarted = shot.run_live(planned, out, execute=False, resume=True,
                                  confirmed_price=True, environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "K"},
                                  client=client, max_polls=1, sleep_fn=lambda _: None)
    assert pending["result"] == "EXISTING_TASK_STILL_PENDING"
    assert restarted["result"] == "EXISTING_TASK_STILL_PENDING"
    assert restarted["submissions"] == 0
    assert count == {"POST": 1, "GET": 2}


def test_resume_unknown_attempt_never_posts(planned, tmp_path, fake_inspection):
    out = tmp_path / "ambiguous"
    out.mkdir()
    (out / "MYCL-001-shot-1.attempt.json").write_text(json.dumps({
        "request_sha256": planned["request_sha256"], "domain": planned["domain"],
        "submissions_attempted": 1, "video_id": None,
    }))
    with pytest.raises(shot.ShotError, match="without previously recorded video_id"):
        shot.run_live(planned, out, execute=False, resume=True, confirmed_price=True,
                      environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "KEY"})


@pytest.mark.parametrize("url", [
    "http://cdn.agnes-ai.com/movie.mp4",
    "https://127.0.0.1/private",
    "https://localhost/foo",
    "https://192.168.10.1/media.mp4",
    "https://user:pw@cdn.agnes-ai.com/x.mp4",
    "file:///etc/passwd",
    "https://cdn.local/foo.mp4",
    "https://169.254.169.254/latest/meta-data",
])
def test_reject_internal_or_unsafe_download_targets(url):
    with pytest.raises(shot.ShotError):
        shot._public_https_url(url)


def test_only_frozen_episode_is_accepted(planned, tmp_path):
    data = json.loads((ROOT / "content/shotlists/MYCL-001-cat-lapping.json").read_text())
    data["episode_id"] = "DIFFERENT-EPISODE"
    fake = tmp_path / "changed.json"
    fake.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(shot.ShotError):
        shot.prepare_plan(fake, ROOT / "content/factpacks/MYCL-001-cat-lapping.json")


def test_reject_duplicate_execution_or_incompatible_resume(planned, tmp_path):
    with pytest.raises(shot.ShotError, match="cannot be used together"):
        shot.run_live(planned, tmp_path / "bad", execute=True, resume=True,
                      confirmed_price=True, environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "KEY"})


def test_mismatched_record_blocks_resume(planned, tmp_path, fake_inspection):
    out = tmp_path / "tampered"
    out.mkdir()
    (out / "MYCL-001-shot-1.attempt.json").write_text(json.dumps({
        "request_sha256": "0" * 64, "domain": planned["domain"],
        "submissions_attempted": 1, "video_id": "accepted_id",
    }))
    with pytest.raises(shot.ShotError, match="does not match"):
        shot.run_live(planned, out, execute=False, resume=True,
                      confirmed_price=True, environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "K"})


def test_local_cli_preview_never_needs_key(capsys):
    code = shot.main([
        "--shotlist", str(ROOT / "content/shotlists/MYCL-001-cat-lapping.json"),
        "--factpack", str(ROOT / "content/factpacks/MYCL-001-cat-lapping.json"),
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "PLAN_ONLY_NO_REQUESTS" in out
    assert "video_id" not in out
