"""Live Chromium click-through of Grok-derived UI + local Mock H3 Bridge.

Creates only blue synthetic MP4s on disposable disk. No AWS/Agnes/network calls.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8767"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO/6G7cAAAAASUVORK5CYII="
)

def get_json(path: str) -> dict:
    with urlopen(BASE + path, timeout=4) as response:
        return json.load(response)

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aniflow-ui-mock-") as d:
        workspace = Path(d)
        frame = workspace / "owner-frame.png"
        frame.write_bytes(PNG)
        env = dict(os.environ)
        env["ANIFLOW_STUDIO_DATA_DIR"] = str(workspace / "runtime")
        for k in list(env):
            if any(secret in k.upper() for secret in ("AWS_SECRET", "AWS_ACCESS_KEY",
                    "AGNES_API_KEY", "MINIMAX_API_KEY", "HF_TOKEN")):
                env.pop(k, None)
        env["PYTHONPATH"] = str(ROOT / "src")
        with (workspace/"server.log").open("wb") as logfile:
            proc = subprocess.Popen(
                [sys.executable, "scripts/run_studio_mock.py"],
                cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT,
            )
            try:
                ready = False
                for _ in range(55):
                    if proc.poll() is not None:
                        raise AssertionError("Local Mock Bridge exited early")
                    try:
                        if get_json("/api/studio/mock/health")["mode"] == "MOCK_ONLY":
                            ready = True
                            break
                    except Exception:
                        time.sleep(0.2)
                if not ready:
                    raise AssertionError("Local Mock Bridge did not become healthy")
                with sync_playwright() as p:
                    chrome = shutil.which("google-chrome") or shutil.which("chromium")
                    browser = p.chromium.launch(
                        executable_path=chrome if chrome else None,
                        headless=True, args=["--no-sandbox"],
                    )
                    context = browser.new_context(accept_downloads=True,viewport={"width":1300,"height":850})
                    def route_handler(route):
                        if route.request.url.startswith(BASE+"/"):
                            route.continue_()
                        else:
                            route.abort()
                    context.route("**/*", route_handler)
                    page = context.new_page()
                    page.goto(BASE+"/", wait_until="domcontentloaded")
                    page.get_by_test_id("strict-mock-banner").wait_for(timeout=15000)
                    assert page.locator("article").count() == 0
                    assert page.get_by_role("button", name="生成视频").is_disabled()
                    page.locator('input[type="file"]').set_input_files(str(frame))
                    page.get_by_role("button", name="生成视频").wait_for(state="visible")
                    assert page.get_by_role("button", name="生成视频").is_enabled()
                    page.get_by_role("button", name="生成视频").click()
                    page.locator("article").first.wait_for(timeout=15000)
                    records = get_json("/api/studio/mock/jobs")
                    assert records["simulation"] is True and len(records["jobs"]) == 1
                    job = records["jobs"][0]
                    assert job["id"].startswith("mock-")
                    page.locator('article button[title="下载"]').first.wait_for(timeout=25000)
                    with page.expect_download(timeout=15000) as dl:
                        page.locator('article button[title="下载"]').first.click()
                    download = dl.value
                    dest = workspace / "download.mp4"
                    download.save_as(dest)
                    expected = (ROOT / "tests/fixtures/MOCK_BLUE_LOCAL_NO_AGNES.mp4").read_bytes()
                    assert hashlib.sha256(dest.read_bytes()).hexdigest() == hashlib.sha256(expected).hexdigest()
                    page.reload(wait_until="domcontentloaded")
                    page.locator("article").first.wait_for(timeout=15000)
                    assert job["id"] in page.locator("article").first.inner_text()
                    assert len(get_json("/api/studio/mock/jobs")["jobs"]) == 1
                    assert get_json("/api/studio/mock/health")["paid_request_count"] == 0
                    # Simulate: server ACCEPTS create, browser loses response.
                    # A mistaken automatic retry would create a third task.
                    page.locator('input[type="file"]').set_input_files(str(frame))
                    def lose_create_response(route):
                        accepted = route.fetch()
                        assert accepted.status == 202
                        route.abort("failed")
                    page.route("**/api/studio/mock/jobs", lose_create_response)
                    page.get_by_role("button", name="生成视频").click()
                    page.get_by_test_id("pending-unknown-create").wait_for(timeout=15000)
                    assert page.get_by_role("button", name="生成视频").is_disabled()
                    assert len(get_json("/api/studio/mock/jobs")["jobs"]) == 2
                    pending = page.evaluate("localStorage.getItem('aniflow.mock.pending_submission.v1')")
                    assert pending and "prompt" not in pending and "data:image" not in pending
                    page.unroute("**/api/studio/mock/jobs")

                    # Restart browser with recovery GET unavailable: keep guard.
                    page.route("**/api/studio/mock/requests/*", lambda route: route.abort("failed"))
                    page.reload(wait_until="domcontentloaded")
                    page.get_by_test_id("pending-unknown-create").wait_for(timeout=15000)
                    assert page.get_by_role("button", name="生成视频").is_disabled()
                    assert len(get_json("/api/studio/mock/jobs")["jobs"]) == 2
                    page.unroute("**/api/studio/mock/requests/*")
                    page.get_by_role("button", name="查询原任务").click()
                    page.wait_for_function(
                        "() => localStorage.getItem('aniflow.mock.pending_submission.v1') === null",
                        timeout=15000,
                    )
                    page.locator("article").first.wait_for(timeout=15000)
                    assert len(get_json("/api/studio/mock/jobs")["jobs"]) == 2
                    print("PASS_BROWSER_UNKNOWN_POST_RECOVERY_READ_ONLY_IDEMPOTENT_NO_REPOST")
                    context.close()
                    browser.close()
                print("PASS_BROWSER_MOCK_IMAGE_UPLOAD_TASK_RESTORE_LOCAL_MP4_DOWNLOAD_NO_AWS")
                return 0
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

if __name__ == "__main__":
    raise SystemExit(main())
