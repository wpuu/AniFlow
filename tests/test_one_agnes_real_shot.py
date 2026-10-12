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

_ORIGINAL_ONCE_ROOT = shot._once_root


@pytest.fixture(autouse=True)
def isolate_single_attempt_ledger(tmp_path, monkeypatch):
    """Never write mock test intent locks into the runner's real user home."""
    monkeypatch.setattr(shot, "_once_root", lambda: tmp_path / "single-attempt-ledger")


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
    elapsed_record = json.loads(record)
    assert elapsed_record["created_at_unix"] <= elapsed_record["accepted_at_unix"]
    assert elapsed_record["accepted_at_unix"] <= elapsed_record["finished_at_unix"]
    assert elapsed_record["elapsed_to_final_result_seconds"] == result[
        "elapsed_to_final_result_seconds"
    ]
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
    data = json.loads((ROOT / "content/shotlists/MYCL-001-cat-lapping.json").read_text(encoding="utf-8"))
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


@pytest.mark.parametrize(
    ("size", "duration_seconds", "expected_result"),
    [
        ("720x1280", 5, "MEDIA_REQUIRES_HUMAN_REVIEW"),
        ("1280x720", 5, "MEDIA_QA_BLOCKED"),
        # Prior code accepted both 4s and 6s under an overly broad 4..6s gate.
        ("720x1280", 4, "MEDIA_QA_BLOCKED"),
        ("720x1280", 6, "MEDIA_QA_BLOCKED"),
        # A nominal 9:16 file is not necessarily Flash's published 720P output.
        ("900x1600", 5, "MEDIA_QA_BLOCKED"),
    ],
)
def test_full_single_shot_path_with_real_ffmpeg_metadata(
    planned, tmp_path, monkeypatch, size, duration_seconds, expected_result
):
    """Real Windows/Linux MP4+ffprobe: provider HTTP itself remains fully mocked.

    This exercises actual video bytes on disk and actual orientation metadata
    verification, not the previous _inspect_clip mock.
    """
    import shutil
    import subprocess

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe are not installed")
    video = tmp_path / "locally-generated-not-agnes.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s={size}:r=4:d={duration_seconds}",
            "-t", str(duration_seconds), "-c:v", "mpeg4", "-q:v", "10",
            "-pix_fmt", "yuv420p", str(video),
        ],
        check=True, capture_output=True, timeout=60,
    )
    payload = video.read_bytes()
    assert len(payload) > 1024
    events = []

    def handler(request: httpx.Request) -> httpx.Response:
        events.append(request.method)
        if request.method == "POST":
            assert request.url.path == "/v1/videos"
            return httpx.Response(201, json={"video_id": "test_local_ffprobe_001"})
        if request.url.path == "/agnesapi":
            return httpx.Response(
                200, json={
                    "status": "completed",
                    "url": "https://video.example.org/synthetic-only.mp4",
                }
            )
        assert request.url.host == "video.example.org"
        return httpx.Response(
            200, headers={"Content-Type": "video/mp4"}, content=payload
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler), trust_env=False
    ) as client:
        result = shot.run_live(
            planned, tmp_path / f"result-{size}-{duration_seconds}", execute=True, resume=False,
            confirmed_price=True,
            environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "NON_SECRET_TEST_ONLY"},
            client=client, poll_interval=0, max_polls=1,
            sleep_fn=lambda _: None,
        )
        cached = shot.run_live(
            planned, tmp_path / f"result-{size}-{duration_seconds}",
            execute=False, resume=True, confirmed_price=False,
            environ={}, client=client,
        )
    assert cached["result"] == expected_result
    assert cached["already_recorded"] is True
    assert cached["submissions"] == 0
    assert cached["network_requests"] == 0
    assert cached["mp4_sha256"] == hashlib.sha256(payload).hexdigest()
    assert events == ["POST", "GET", "GET"]
    assert result["result"] == expected_result
    assert result["submissions"] == 1
    assert result["media_check"] == (
        "METADATA_OK_HUMAN_QA_REQUIRED"
        if expected_result == "MEDIA_REQUIRES_HUMAN_REVIEW"
        else "BLOCKED"
    )
    assert result["manual_viewing_required"] is True
    assert result["pixel_orientation_verified"] is False
    assert result["mp4_sha256"] == hashlib.sha256(payload).hexdigest()
    assert abs(result["actual_duration_seconds"] - duration_seconds) <= 0.15
    assert result["display_dimensions"] == [int(x) for x in size.split("x")]
    if duration_seconds != 5:
        assert any("5-second shot" in x for x in result["blockers"])
    if size == "900x1600":
        assert any("720x1280" in x for x in result["blockers"])
    record = (tmp_path / f"result-{size}-{duration_seconds}" / "MYCL-001-shot-1.attempt.json").read_text(
        encoding="utf-8"
    )
    assert "NON_SECRET_TEST_ONLY" not in record
    assert "video.example.org" not in record
    saved = json.loads(record)
    assert saved["display_dimensions"] == [int(x) for x in size.split("x")]
    assert abs(saved["actual_duration_seconds"] - duration_seconds) <= 0.15


def test_new_output_directory_cannot_resubmit_same_shot(planned, tmp_path, fake_inspection):
    """Changing the folder after HTTP 503 must not create a second task."""
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(503, json={"code": "video_queue_full"})
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        first = shot.run_live(
            planned, tmp_path / "first-folder", execute=True, resume=False,
            confirmed_price=True,
            environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "TEST_KEY_1"},
            client=client,
        )
        assert first["result"] == "REJECTED_NO_VIDEO_ID"
        with pytest.raises(shot.ShotError, match="already reserved"):
            shot.run_live(
                planned, tmp_path / "different-folder", execute=True, resume=False,
                confirmed_price=True,
                environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "TEST_KEY_1"},
                client=client,
            )
    assert calls == ["POST"]
    assert not (tmp_path / "different-folder/MYCL-001-shot-1.attempt.json").exists()
    ledger = tmp_path / "single-attempt-ledger/MYCL-001-shot-1.once.json"
    record = json.loads(ledger.read_text(encoding="utf-8"))
    assert record["request_sha256"] == planned["request_sha256"]
    assert record["output_folder"] == "first-folder"
    assert "TEST_KEY_1" not in ledger.read_text(encoding="utf-8")
    assert "file://" not in ledger.read_text(encoding="utf-8")


def test_changing_api_domain_does_not_bypass_single_shot_ledger(
    planned, tmp_path, fake_inspection
):
    """A global-to-China domain switch must not silently double-bill."""
    china = shot.prepare_plan(
        ROOT / "content/shotlists/MYCL-001-cat-lapping.json",
        ROOT / "content/factpacks/MYCL-001-cat-lapping.json",
        domain="china",
    )
    assert china["domain"] != planned["domain"]
    methods = []
    def handler(request):
        methods.append(request.method)
        return httpx.Response(429, json={"code": "rate_limited"})
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        shot.run_live(
            planned, tmp_path / "global", execute=True, resume=False,
            confirmed_price=True,
            environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "ONE_KEY"},
            client=client,
        )
        with pytest.raises(shot.ShotError, match="already reserved"):
            shot.run_live(
                china, tmp_path / "china", execute=True, resume=False,
                confirmed_price=True,
                environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "ONE_KEY"},
                client=client,
            )
    assert methods == ["POST"]


def test_network_ambiguity_guard_survives_new_output_folder(
    planned, tmp_path, fake_inspection
):
    """When the first POST timed out, duplicate submissions must remain blocked."""
    calls = []
    def handler(request):
        calls.append(request.method)
        raise httpx.ReadTimeout("response lost after possible submit")
    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        with pytest.raises(shot.ShotError, match="SUBMISSION_AMBIGUOUS"):
            shot.run_live(
                planned, tmp_path / "uncertain", execute=True, resume=False,
                confirmed_price=True,
                environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "ONE_KEY"},
                client=client,
            )
        with pytest.raises(shot.ShotError, match="already reserved"):
            shot.run_live(
                planned, tmp_path / "new-uncertain", execute=True, resume=False,
                confirmed_price=True,
                environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "ONE_KEY"},
                client=client,
            )
    assert calls == ["POST"]


def test_guard_is_exclusive_between_concurrent_process_intents(planned, tmp_path):
    """File-exclusive reservation allows one winner even with concurrent attempts."""
    from concurrent.futures import ThreadPoolExecutor

    ledger = tmp_path / "single-attempt-ledger"
    output = tmp_path / "planned-video-dir"
    def reserve(_):
        try:
            shot._reserve_one_submission(planned, output)
            return "WIN"
        except shot.ShotError:
            return "BLOCKED"

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(reserve, range(6)))
    assert outcomes.count("WIN") == 1
    assert outcomes.count("BLOCKED") == 5
    saved = json.loads(
        (ledger / "MYCL-001-shot-1.once.json").read_text(encoding="utf-8")
    )
    assert saved["intent"] == "MYCL-001-shot-1"


def test_default_plan_never_creates_single_attempt_guard(planned, tmp_path):
    result = shot.run_live(
        planned, tmp_path / "no-run", execute=False, resume=False,
        confirmed_price=False, environ={},
    )
    assert result["submissions"] == 0
    assert not (tmp_path / "single-attempt-ledger").exists()


@pytest.fixture
def fake_rebuild_persistent_codespace(tmp_path, monkeypatch):
    """Simulate a Codespace with persistent /workspaces and disposable /home."""
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    persistent = workspaces / ".aniflow-private"
    persistent.mkdir(mode=0o700)
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.setattr(shot, "_codespace_workspace_base", lambda: workspaces)
    # The test module's global fixture isolates home-ledger behavior; restore
    # the real selector for these explicit Codespaces-specific cases.
    monkeypatch.setattr(shot, "_once_root", _ORIGINAL_ONCE_ROOT)
    return persistent


def test_codespaces_ledger_uses_rebuild_persistent_volume(
    planned, tmp_path, monkeypatch, fake_rebuild_persistent_codespace
):
    persistent = fake_rebuild_persistent_codespace
    expected = persistent / "single-attempt-ledger"
    assert shot._once_root() == expected
    monkeypatch.setenv("HOME", str(tmp_path / "disposable-home-one"))
    shot._reserve_one_submission(planned, persistent / "first")
    guard = expected / "MYCL-001-shot-1.once.json"
    assert guard.is_file()

    # Rebuild scenario: container's home is erased/recreated while the mounted
    # /workspaces volume remains unchanged.
    monkeypatch.setenv("HOME", str(tmp_path / "disposable-home-after-rebuild"))
    assert shot._once_root() == expected
    with pytest.raises(shot.ShotError, match="already reserved"):
        shot._reserve_one_submission(planned, persistent / "different-folder")
    assert guard.is_file()


def test_codespaces_disposable_home_video_folder_is_refused(
    tmp_path, fake_rebuild_persistent_codespace
):
    ephemeral_home = tmp_path / "disposable-home"
    ephemeral_home.mkdir()
    with pytest.raises(shot.ShotError, match="home-directory videos are erased"):
        shot._output_dir(ephemeral_home / "mycl001-shot1", create=True)
    assert not (ephemeral_home / "mycl001-shot1").exists()
    allowed = shot._output_dir(
        fake_rebuild_persistent_codespace / "mycl001-shot1", create=True
    )
    assert allowed.is_dir()
    assert allowed.parent == fake_rebuild_persistent_codespace


def test_codespaces_missing_persistent_volume_fails_closed(
    tmp_path, monkeypatch, fake_rebuild_persistent_codespace
):
    unavailable = tmp_path / "missing-workspaces"
    monkeypatch.setattr(shot, "_codespace_workspace_base", lambda: unavailable)
    with pytest.raises(shot.ShotError, match="persistent /workspaces volume"):
        shot._once_root()
    with pytest.raises(shot.ShotError, match="persistent /workspaces volume"):
        shot._output_dir(tmp_path / "other" / "video", create=True)


def test_codespaces_symlinked_private_volume_fails_closed(
    tmp_path, monkeypatch, fake_rebuild_persistent_codespace
):
    original = fake_rebuild_persistent_codespace
    original.rmdir()
    other = tmp_path / "outside"
    other.mkdir()
    try:
        original.symlink_to(other, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Filesystem does not support symlinks")
    with pytest.raises(shot.ShotError, match="must not be a symlink"):
        shot._once_root()


def test_codespaces_one_post_survives_simulated_home_reset(
    planned, tmp_path, monkeypatch, fake_rebuild_persistent_codespace, fake_inspection
):
    persistent = fake_rebuild_persistent_codespace
    events = []

    def handler(request):
        events.append(request.method)
        return httpx.Response(503, json={"code": "video_queue_full"})

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        result = shot.run_live(
            planned, persistent / "first-job", execute=True, resume=False,
            confirmed_price=True,
            environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "TEST_ONLY"},
            client=client,
        )
        assert result["result"] == "REJECTED_NO_VIDEO_ID"
        monkeypatch.setenv("HOME", str(tmp_path / "newly-built-container-home"))
        with pytest.raises(shot.ShotError, match="already reserved"):
            shot.run_live(
                planned, persistent / "second-job", execute=True, resume=False,
                confirmed_price=True,
                environ={"ANIFLOW_SINGLE_SHOT_API_KEY": "TEST_ONLY"},
                client=client,
            )
    assert events == ["POST"]
    assert (persistent / "first-job/MYCL-001-shot-1.attempt.json").is_file()
    assert (persistent / "single-attempt-ledger/MYCL-001-shot-1.once.json").is_file()


def test_first_submission_time_survives_acceptance_and_completion(planned, tmp_path, monkeypatch):
    """Never overwrite the original submission timestamp when status changes."""
    from types import SimpleNamespace

    clock = [120000]
    monkeypatch.setattr(shot, "time", SimpleNamespace(time=lambda: clock[0]))
    evidence = tmp_path / "timestamps.json"
    begin = shot._save_attempt(
        evidence, planned, status="SUBMISSION_ATTEMPT_UNCONFIRMED"
    )
    assert begin["created_at_unix"] == 120000
    assert begin["response_at_unix"] is None

    clock[0] = 120009
    accepted = shot._save_attempt(
        evidence, planned, status="ACCEPTED_SINGLE_VIDEO",
        video_id="video_accepted", http_status=200,
    )
    assert accepted["created_at_unix"] == 120000
    assert accepted["response_at_unix"] == 120009
    assert accepted["accepted_at_unix"] == 120009
    assert accepted["response_latency_seconds"] == 9

    clock[0] = 121006
    reread = json.loads(evidence.read_text(encoding="utf-8"))
    assert shot._record_finished(reread) == 1006
    assert reread["elapsed_to_final_result_seconds"] == 1006
    assert reread["finished_at_unix"] == 121006
    assert reread["created_at_unix"] == 120000


def test_rejected_queue_full_preserves_initial_submit_time(planned, tmp_path, monkeypatch):
    """Confirmed 503 rejection is counted, not erased by the response update."""
    from types import SimpleNamespace

    clock = [250000]
    monkeypatch.setattr(shot, "time", SimpleNamespace(time=lambda: clock[0]))
    evidence = tmp_path / "rejected.json"
    shot._save_attempt(evidence, planned, status="SUBMISSION_ATTEMPT_UNCONFIRMED")
    clock[0] += 12
    rejection = shot._save_attempt(
        evidence, planned, status="REJECTED_NO_VIDEO_ID",
        http_status=503, code="video_queue_full",
    )
    assert rejection["created_at_unix"] == 250000
    assert rejection["response_at_unix"] == 250012
    assert rejection["response_latency_seconds"] == 12
    assert rejection["accepted_at_unix"] is None
    assert rejection["video_id"] is None
    assert rejection["error_code"] == "video_queue_full"


def test_timestamp_update_fails_closed_if_original_marker_tampered(planned, tmp_path):
    evidence = tmp_path / "tampered.json"
    evidence.write_text(
        json.dumps({
            "request_sha256": "0" * 64,
            "status": "SUBMISSION_ATTEMPT_UNCONFIRMED",
            "created_at_unix": 100,
        }),
        encoding="utf-8",
    )
    with pytest.raises(shot.ShotError, match="Original attempt record changed"):
        shot._save_attempt(
            evidence, planned, status="ACCEPTED_SINGLE_VIDEO",
            video_id="video_accepted",
        )
    assert json.loads(evidence.read_text(encoding="utf-8"))["request_sha256"] == "0" * 64


def test_resume_after_crash_between_download_and_record_finalization(
    planned, tmp_path, fake_inspection
):
    """Local MP4 with accepted ID must never be redownloaded or called 'verified'."""
    out = tmp_path / "interrupted-after-video"
    out.mkdir()
    record = out / "MYCL-001-shot-1.attempt.json"
    shot._save_attempt(record, planned, status="SUBMISSION_ATTEMPT_UNCONFIRMED")
    shot._save_attempt(
        record, planned, status="ACCEPTED_SINGLE_VIDEO", video_id="real_id_001",
    )
    before = record.read_bytes()
    data = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 3000
    (out / "MYCL-001-shot-1.mp4").write_bytes(data)
    calls = []

    def handler(request):
        calls.append(request.method)
        raise AssertionError("No network must be used when reconciling local MP4")

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        result = shot.run_live(
            planned, out, execute=False, resume=True, confirmed_price=False,
            environ={}, client=client,
        )
    assert result["result"] == "LOCAL_MP4_NEEDS_ORIGIN_RECONCILIATION"
    assert result["submissions"] == 0
    assert result["network_requests"] == 0
    assert result["provider_provenance_verified"] is False
    assert result["mp4_sha256"] == hashlib.sha256(data).hexdigest()
    assert result["attempt_record_unchanged"] is True
    assert record.read_bytes() == before
    assert calls == []


def test_finished_video_resume_refuses_digest_mismatch_without_network(
    planned, tmp_path, fake_inspection
):
    out = tmp_path / "recorded-finished"
    out.mkdir()
    record = out / "MYCL-001-shot-1.attempt.json"
    shot._save_attempt(record, planned, status="SUBMISSION_ATTEMPT_UNCONFIRMED")
    shot._save_attempt(
        record, planned, status="ACCEPTED_SINGLE_VIDEO", video_id="video_001",
    )
    media = out / "MYCL-001-shot-1.mp4"
    media.write_bytes(b"MOCK-MP4" * 400)
    evidence = json.loads(record.read_text(encoding="utf-8"))
    evidence["status"] = "MEDIA_REQUIRES_HUMAN_REVIEW"
    evidence["mp4_bytes"] = media.stat().st_size
    evidence["mp4_sha256"] = hashlib.sha256(media.read_bytes()).hexdigest()
    shot._write_json(record, evidence, replace=True)

    # Tampering after original acceptance cannot be hidden by a fresh retrieve.
    media.write_bytes(b"CHANGED!" * 400)
    with pytest.raises(shot.ShotError, match="SHA-256 or size differs"):
        shot.run_live(
            planned, out, execute=False, resume=True, confirmed_price=False,
            environ={},
        )


def test_failed_task_is_replayed_locally_without_agnes_key(
    planned, tmp_path, fake_inspection
):
    out = tmp_path / "failed-provider"
    out.mkdir()
    record = out / "MYCL-001-shot-1.attempt.json"
    shot._save_attempt(record, planned, status="SUBMISSION_ATTEMPT_UNCONFIRMED")
    shot._save_attempt(
        record, planned, status="ACCEPTED_SINGLE_VIDEO", video_id="upstream_failed",
    )
    e = json.loads(record.read_text(encoding="utf-8"))
    e["status"] = "FAILED_UPSTREAM"
    e["error_code"] = "video_generation_failed"
    e["elapsed_to_final_result_seconds"] = 132
    shot._write_json(record, e, replace=True)
    result = shot.run_live(
        planned, out, execute=False, resume=True, confirmed_price=False,
        environ={},
    )
    assert result["result"] == "FAILED_UPSTREAM"
    assert result["submissions"] == 0
    assert result["network_requests"] == 0
    assert result["error_code"] == "video_generation_failed"
    assert result["elapsed_to_final_result_seconds"] == 132


def test_partial_video_requires_manual_inspection_without_a_get(
    planned, tmp_path, fake_inspection
):
    out = tmp_path / "unfinished-download"
    out.mkdir()
    record = out / "MYCL-001-shot-1.attempt.json"
    shot._save_attempt(record, planned, status="SUBMISSION_ATTEMPT_UNCONFIRMED")
    shot._save_attempt(
        record, planned, status="ACCEPTED_SINGLE_VIDEO", video_id="video_001",
    )
    (out / "MYCL-001-shot-1.part").write_bytes(b"partial-file")
    with pytest.raises(shot.ShotError, match="Partial MP4 remains"):
        shot.run_live(
            planned, out, execute=False, resume=True, confirmed_price=False,
            environ={},
        )
    assert (out / "MYCL-001-shot-1.part").read_bytes() == b"partial-file"


def test_finalized_record_without_video_stops_before_any_network(
    planned, tmp_path, fake_inspection
):
    out = tmp_path / "vanished-video"
    out.mkdir()
    record = out / "MYCL-001-shot-1.attempt.json"
    shot._save_attempt(record, planned, status="SUBMISSION_ATTEMPT_UNCONFIRMED")
    shot._save_attempt(
        record, planned, status="ACCEPTED_SINGLE_VIDEO", video_id="video_001",
    )
    evidence = json.loads(record.read_text(encoding="utf-8"))
    evidence["status"] = "MEDIA_QA_BLOCKED"
    evidence["mp4_sha256"] = "1" * 64
    evidence["mp4_bytes"] = 4096
    shot._write_json(record, evidence, replace=True)
    with pytest.raises(shot.ShotError, match="MP4 is missing"):
        shot.run_live(
            planned, out, execute=False, resume=True, confirmed_price=False,
            environ={},
        )

