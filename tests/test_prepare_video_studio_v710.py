"""Standard-library-only tests; no network, GitHub writes or genuine API keys."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_video_studio_v710.py"
SPEC = importlib.util.spec_from_file_location("prepare_video_studio_v710", SCRIPT)
assert SPEC and SPEC.loader
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class PrepareStudioTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name)
        self.destination = self.home / "external" / "studio-v710"
        self.git_calls = []
        self.fake_head = app.COMMIT
        self.dirty = False
        self._make_checkout = True

    def write_checkout(self, target: Path):
        (target / ".git").mkdir(parents=True)
        for name in app.SOURCE_FILES:
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test fixture", encoding="utf-8")
        (target / "core/api/agnes_video.py").write_text("BusyTracker is_busy_signal ring.next() ring.rotate()")
        (target / "core/api/retry_policy.py").write_text("BusyTracker is_busy_signal")
        (target / "core/api/key_manager.py").write_text("mark_auth_failed")
        (target / "docs/public/usage.md").write_text("AGNES_FIX_V25_PORTRAIT_ROTATION")

    def fake_git(self, *args):
        self.git_calls.append(args)
        if args[0] == "clone":
            dest = Path(args[-1])
            if self._make_checkout:
                self.write_checkout(dest)
            else:
                raise app.SafetyError("Simulated network failure")
            return ""
        if "--show-toplevel" in args:
            return str(Path(args[1]).resolve())
        if "HEAD" in args:
            return self.fake_head
        if "--porcelain" in args:
            return " M tracked.py" if self.dirty else ""
        raise AssertionError(f"unexpected git command: {args}")

    def test_git_disables_credential_helper(self):
        from subprocess import CompletedProcess
        fake = CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")
        with patch.object(app.subprocess, "run", return_value=fake) as runner:
            self.assertEqual(app._git("--version"), "OK")
        command = runner.call_args.args[0]
        self.assertEqual(command[:3], ["git", "-c", "credential.helper="])

    def test_default_plan_does_not_write_or_call_git(self):
        with patch.object(app, "_git", self.fake_git):
            result = app.plan(self.destination)
        self.assertEqual(result["result"], "PLAN_ONLY_NO_CHANGES")
        self.assertFalse(self.destination.parent.exists())
        self.assertEqual(self.git_calls, [])
        self.assertFalse(result["will_copy_keys"])

    def test_explicit_install_is_pinned_and_does_not_start_services(self):
        with patch.object(app, "_git", self.fake_git):
            result = app.install(self.destination)
        self.assertTrue(self.destination.exists())
        self.assertEqual(result["result"], "PINNED_SOURCE_PREPARED_NOT_STARTED")
        self.assertEqual(result["commit"], app.COMMIT)
        self.assertFalse(result["packages_installed"])
        self.assertFalse(result["service_started"])
        self.assertEqual(self.git_calls[0][:5], ("clone", "--depth", "1", "--branch", "v7.1.0"))
        self.assertNotIn("AGNES_API_KEY", str(result))

    def test_existing_destination_never_overwritten(self):
        self.destination.mkdir(parents=True)
        marker = self.destination / "do_not_erase.txt"
        marker.write_text("keep")
        with self.assertRaises(app.SafetyError):
            app.install(self.destination)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(self.git_calls, [])

    def test_wrong_sha_fails_closed_without_publishing(self):
        self.fake_head = "0" * 40
        with patch.object(app, "_git", self.fake_git):
            with self.assertRaisesRegex(app.SafetyError, "does not match"):
                app.install(self.destination)
        self.assertFalse(self.destination.exists())

    def test_invalid_source_fails_closed_without_publishing(self):
        def partial_git(*args):
            result = self.fake_git(*args)
            if args[0] == "clone":
                (Path(args[-1]) / "core/api/retry_policy.py").unlink()
            return result
        with patch.object(app, "_git", partial_git):
            with self.assertRaisesRegex(app.SafetyError, "source files missing"):
                app.install(self.destination)
        self.assertFalse(self.destination.exists())

    def test_failed_clone_keeps_destination_absent(self):
        self._make_checkout = False
        with patch.object(app, "_git", self.fake_git):
            with self.assertRaises(app.SafetyError):
                app.install(self.destination)
        self.assertFalse(self.destination.exists())

    def test_git_modified_tracked_files_block_verification(self):
        self.write_checkout(self.destination)
        self.dirty = True
        with patch.object(app, "_git", self.fake_git):
            with self.assertRaisesRegex(app.SafetyError, "modified"):
                app.verify_existing(self.destination)

    def test_reject_repo_internal_target(self):
        repo_inside = Path(app.__file__).resolve().parents[1] / "not_safe"
        with self.assertRaisesRegex(app.SafetyError, "inside the AniFlow Git repository"):
            app.plan(repo_inside)

    def test_verify_existing_never_reads_local_env(self):
        self.write_checkout(self.destination)
        secret = self.destination / ".env"
        secret.write_text("AGNES_API_KEY=TEST_SECRET_12345")
        with patch.object(app, "_git", self.fake_git):
            result = app.verify_existing(self.destination)
        self.assertNotIn("TEST_SECRET", str(result))
        self.assertEqual(secret.read_text(), "AGNES_API_KEY=TEST_SECRET_12345")

    def test_unknown_repo_root_is_blocked(self):
        self.write_checkout(self.destination)
        def fake_git(*args):
            if "--show-toplevel" in args:
                return str(self.home)
            return self.fake_git(*args)
        with patch.object(app, "_git", fake_git):
            with self.assertRaisesRegex(app.SafetyError, "does not equal"):
                app.verify_existing(self.destination)


if __name__ == "__main__":
    unittest.main()
