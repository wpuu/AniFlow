"""Real Chromium click-through of existing AniFlow 9-Key UI; NO Agnes network or secrets.

Uses a local fake Agnes transport only, checks task create/status, first-shot
preset, browser localStorage recovery, failure guard, reference mode, duplicate
Keys, sanitized summary and an explicitly MOCK-watermarked screenshot.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8765"
FAKE_VALID = "E2E_MOCK_VALID_KEY_NOT_A_REAL_SECRET"
FAKE_TIMEOUT = "E2E_MOCK_TIMEOUT_KEY_NOT_A_REAL_SECRET"


def mock_state() -> dict:
    with urllib.request.urlopen(BASE + "/__e2e_state", timeout=4) as stream:
        return json.load(stream)


def await_local_bridge(process: subprocess.Popen, limit: float = 35.0) -> None:
    end = time.monotonic() + limit
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError("E2E fake Bridge process exited before readiness")
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=1) as response:
                if json.load(response).get("frontend_ready"):
                    return
        except (OSError, ValueError):
            time.sleep(0.3)
    raise RuntimeError("Timed out starting the fake local AniFlow Bridge")


def configure_local_only_network(context) -> None:
    def only_local(route):
        url = route.request.url
        if url.startswith(BASE + "/"):
            route.continue_()
        else:
            route.abort()
    context.route("**/*", only_local)


def fill_single_key_and_first_shot(page, key: str) -> None:
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.get_by_placeholder("请输入 Key 1（API Key）").fill(key)
    page.get_by_role("button", name="载入雪所长首镜头 · 5秒").click()
    prompt = page.get_by_placeholder("描述画面、动作、镜头、光线与风格。").input_value()
    assert "ceramic water bowl" in prompt, "Frozen first-shot bowl is missing"
    assert "needle-felt" in prompt, "Character texture was lost"
    assert len(prompt) > 700, "Frozen first-shot prompt unexpectedly shortened"


def generate_fake_mp4(path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required to generate a clearly synthetic local test clip")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=360x640:r=12",
        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if not path.is_file() or path.stat().st_size < 1024:
        raise RuntimeError("Mock video asset could not be generated")


def test_browser(screenshot: Path) -> None:
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        raise RuntimeError("No Chromium/Chrome browser installed on CI image")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=chrome,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = browser.new_context(
                viewport={"width": 1340, "height": 900},
                permissions=["clipboard-read", "clipboard-write"],
            )
            configure_local_only_network(context)
            page = context.new_page()
            fill_single_key_and_first_shot(page, FAKE_VALID)
            assert mock_state()["create_calls"] == 0, "Preset must not create a task"
            page.get_by_role("button", name="生成视频", exact=True).click()
            page.locator('video[src*="/__e2e_fake_video.mp4"]').wait_for(timeout=25_000)
            current = mock_state()
            assert current["create_calls"] == 1, "One manual click must create exactly one fake task"
            assert current["status_calls"] >= 1, "UI did not query the original fake video_id"
            assert current["last_payload"]["mode"] == "text", "Wrong mode sent for frozen first shot"
            assert current["last_payload"]["seconds"] == "5"
            assert current["last_payload"]["aspect_ratio"] == "9:16"

            page.get_by_role("button", name="复制9-Key安全测试摘要").click()
            clipboard = page.evaluate("() => navigator.clipboard.readText()")
            report = json.loads(clipboard)
            assert report["keys"][0]["status"] == "completed"
            assert report["keys"][0]["has_download_url"] is True
            for protected in (FAKE_VALID, "e2e_local_mock_video_1",
                              "__e2e_fake_video.mp4", "ceramic water bowl"):
                assert protected not in clipboard, "Private task material leaked in copied summary"

            page.reload(wait_until="domcontentloaded")
            page.locator('video[src*="/__e2e_fake_video.mp4"]').wait_for(timeout=15_000)
            assert mock_state()["create_calls"] == 1, "Reload must not create another task"
            page.evaluate("""() => {
                const tag = document.createElement('div');
                tag.textContent = 'MOCK BROWSER TEST ONLY — NO REAL AGNES VIDEO / NO API KEY';
                tag.style.cssText = 'position:sticky;top:0;z-index:10000;padding:12px;background:#fef3c7;color:#92400e;font:bold 17px Arial;text-align:center';
                document.body.prepend(tag);
            }""")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
            context.close()

            uncertain = browser.new_context(viewport={"width": 1000, "height": 850})
            configure_local_only_network(uncertain)
            page2 = uncertain.new_page()
            fill_single_key_and_first_shot(page2, FAKE_TIMEOUT)
            page2.get_by_role("button", name="生成视频", exact=True).click()
            page2.get_by_role("button", name="待核实·禁止重发", exact=True).wait_for(timeout=15_000)
            assert page2.get_by_role("button", name="待核实·禁止重发", exact=True).is_disabled()
            after_uncertain = mock_state()
            assert after_uncertain["create_calls"] == 2
            assert after_uncertain["has_seen_timeout"] is True
            page2.reload(wait_until="domcontentloaded")
            assert page2.get_by_role("button", name="待核实·禁止重发", exact=True).is_disabled()
            assert mock_state()["create_calls"] == 2, "Refresh must not repeat an ambiguous video POST"
            uncertain.close()

            refctx = browser.new_context(viewport={"width": 1150, "height": 850})
            configure_local_only_network(refctx)
            page3 = refctx.new_page()
            page3.goto(BASE + "/", wait_until="domcontentloaded")
            page3.get_by_placeholder("请输入 Key 1（API Key）").fill(FAKE_VALID)
            page3.get_by_role("button", name="载入角色参考图测试 · 5秒").click()
            prompt = page3.get_by_placeholder("描述画面、动作、镜头、光线与风格。").input_value()
            assert "<Picture 1>" in prompt
            assert mock_state()["create_calls"] == 2, "Loading a reference must not submit"
            page3.get_by_role("button", name="生成视频", exact=True).click()
            page3.locator('video[src*="/__e2e_fake_video.mp4"]').wait_for(timeout=25_000)
            payload = mock_state()["last_payload"]
            assert mock_state()["create_calls"] == 3
            assert payload["mode"] == "reference"
            assert len(payload["images"]) == 1
            assert "agnes-felt-test-frame.png" in payload["images"][0]
            assert "first_frame" not in payload
            refctx.close()

            dups = browser.new_context(viewport={"width": 1050, "height": 800})
            configure_local_only_network(dups)
            page4 = dups.new_page()
            page4.goto(BASE + "/", wait_until="domcontentloaded")
            page4.locator('input[type="number"][max="9"]').fill("2")
            page4.get_by_placeholder("请输入 Key 1（API Key）").fill(FAKE_VALID)
            page4.get_by_placeholder("请输入 Key 2（API Key）").fill(FAKE_VALID)
            page4.get_by_role("button", name="载入雪所长首镜头 · 5秒").click()
            page4.get_by_role("button", name="一键生成全部可用 Key").click()
            page4.get_by_text("检测到重复 Agnes API Key", exact=False).wait_for(timeout=10_000)
            assert mock_state()["create_calls"] == 3, "Duplicate slots must block an entire batch"
            dups.close()

            # Nine DISTINCT fake Keys simultaneously: actual browser click, exactly
            # nine independent local mock POSTs and nine GET-polled video IDs.
            batchctx = browser.new_context(viewport={"width": 1300, "height": 900})
            configure_local_only_network(batchctx)
            batch = batchctx.new_page()
            batch.goto(BASE + "/", wait_until="domcontentloaded")
            batch.locator('input[type="number"][max="9"]').fill("9")
            for idx in range(1, 10):
                batch.get_by_placeholder(f"请输入 Key {idx}（API Key）").fill(
                    f"E2E_MOCK_SLOT_KEY_{idx}"
                )
            batch.get_by_role("button", name="载入雪所长首镜头 · 5秒").click()
            prior = mock_state()["create_calls"]
            batch.once("dialog", lambda dialog: dialog.accept())
            batch.get_by_role("button", name="一键生成全部可用 Key").click()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and mock_state()["batch_create_calls"] < 9:
                time.sleep(0.3)
            state = mock_state()
            assert state["batch_create_calls"] == 9, "Nine distinct Keys did not submit nine tasks"
            assert state["create_calls"] == prior + 9, "Nine-key batch submitted extra requests"
            assert len(set(state["batch_video_ids"])) == 9
            assert set(state["batch_video_ids"]) == {
                f"e2e_local_mock_batch_{idx}" for idx in range(1, 10)
            }
            for idx in range(1, 10):
                batch.get_by_test_id(f"key-tab-{idx}").click()
                batch.locator('video[src*="/__e2e_fake_video.mp4"]').wait_for(timeout=25_000)
                assert f"历史记录（{idx}）" in batch.content()
                assert batch.get_by_test_id(f"key-progress-{idx}").inner_text() == "100%"
                assert batch.get_by_test_id("selected-progress").inner_text() == "100%"
            assert mock_state()["create_calls"] == prior + 9, (
                "Switching Key tabs must not submit another generation"
            )
            batchctx.close()

            # Reproduce the user's screenshot: nine stored attempts without video IDs.
            oldctx = browser.new_context(viewport={"width": 1500, "height": 920})
            configure_local_only_network(oldctx)
            old = oldctx.new_page()
            old.goto(BASE + "/", wait_until="domcontentloaded")
            old.evaluate("""() => {
              const attempts = {};
              for (let i = 0; i < 9; i++) {
                attempts[String(i)] = {
                  attemptId: 'old-task-without-id-' + i,
                  keyIndex: i,
                  modelKey: 'flash25',
                  createdAt: Date.now() - 3600000,
                  videoId: null,
                };
              }
              localStorage.setItem('aniflow_video_submission_guards_v1', JSON.stringify(attempts));
              localStorage.setItem('agnes_video_key_count_v1', '9');
              localStorage.setItem('agnes_video_api_keys_v1',
                JSON.stringify(Array.from({length: 9}, (_, i) => 'E2E_MOCK_SLOT_KEY_' + (i+1))));
            }""")
            old.reload(wait_until="domcontentloaded")
            action = old.get_by_role("button", name="一次整理无编号旧记录（保留备份）")
            action.wait_for(timeout=12_000)
            assert old.get_by_test_id("key-progress-9").inner_text() == "0%"
            assert "人工核实后解锁" not in old.content()
            before = mock_state()["create_calls"]
            old.once("dialog", lambda dialog: dialog.accept())
            action.click()
            action.wait_for(state="detached", timeout=12_000)
            audit = old.evaluate("""() => ({
              remaining: Object.keys(JSON.parse(localStorage.getItem('aniflow_video_submission_guards_v1'))),
              archived: JSON.parse(localStorage.getItem('aniflow_video_archived_noid_attempts_v1')),
            })""")
            assert audit["remaining"] == []
            assert len(audit["archived"]) == 9
            assert all(a["videoId"] is None for a in audit["archived"])
            assert mock_state()["create_calls"] == before, "Archiving must never create another video"
            old.get_by_test_id("key-tab-9").click()
            assert "第 9 个 Key · 视频预览" in old.content()
            assert old.get_by_test_id("selected-progress").inner_text() == "0%"
            old.reload(wait_until="domcontentloaded")
            assert old.get_by_test_id("key-tab-9").is_visible()
            assert old.get_by_role("button", name="一次整理无编号旧记录（保留备份）").count() == 0

            # Only the documented two video models; paid selection must require opt-in.
            assert old.get_by_text("Agnes Video 2.5 · 付费", exact=True).is_visible()
            assert old.get_by_text("Agnes Video V2.0", exact=True).count() == 0
            old.get_by_text("Agnes Video 2.5 · 付费", exact=True).click()
            old.get_by_role("button", name="载入雪所长首镜头 · 5秒").click()
            old.once("dialog", lambda dialog: dialog.dismiss())
            old.get_by_role("button", name="生成视频 · Key1").click()
            assert mock_state()["create_calls"] == before, "Dismissing paid confirmation must send zero POST"
            oldctx.close()

            print("PASS_REAL_BROWSER_MOCK_AGNES_FIRST_SHOT_CREATE_QUERY_VIDEO_RELOAD")
            print("PASS_REAL_BROWSER_AMBIGUOUS_POST_FAIL_CLOSED_NO_RESUBMIT")
            print("PASS_REAL_BROWSER_REFERENCE_VS_FIRST_FRAME_AND_DUPLICATE_KEY_BLOCK")
            print("PASS_REAL_BROWSER_REDACTED_CLIPBOARD_SUMMARY")
            print("PASS_REAL_BROWSER_NINE_UNIQUE_KEYS_BATCH_NINE_IDS_NO_DUPLICATES")
            print("PASS_REAL_BROWSER_NINE_OLD_GUARDS_SINGLE_ARCHIVE_NUMERIC_TABS_PROGRESS")
            print("PASS_REAL_BROWSER_FLASH_DEFAULT_PAID_CONFIRM_CANCELS_WITH_NO_POST")
            print("BROWSER_MOCK_CREATE_CALLS=12, REAL_AGNES_CREATE_CALLS=0")
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path, default=Path("e2e-results/fake-agnes-ui.png"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aniflow-safe-browser-mock-") as tmp:
        video = Path(tmp) / "NOT_A_REAL_AGNES_VIDEO.mp4"
        logfile = Path(tmp) / "mock-server.log"
        generate_fake_mp4(video)
        env = dict(os.environ)
        env["ANIFLOW_E2E_FAKE_VIDEO_FILE"] = str(video)
        # Refuse inherited credential names, even though httpx.MockTransport
        # ensures the fake server cannot contact Agnes.
        for name in ("AGNES_API_KEYS", "AGNES_API_KEY", "ANIFLOW_SINGLE_SHOT_API_KEY"):
            env.pop(name, None)
        with logfile.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "scripts.browser_e2e_mock:app",
                 "--host", "127.0.0.1", "--port", "8765", "--no-access-log",
                 "--log-level", "error"],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                await_local_bridge(process)
                test_browser(args.screenshot.resolve())
            except Exception:
                # Server log only contains synthetic requests; don't dump
                # browser localStorage or any external user information.
                print("E2E_ERROR: " + logfile.read_text(encoding="utf-8")[-1500:])
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
