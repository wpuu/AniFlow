"""Offline, standard-library-only regression checks for the read-only compatibility audit."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1] / "scripts" / "audit_video_studio_v710.py"
spec = importlib.util.spec_from_file_location("audit_video_studio_v710", AUDIT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VideoStudioAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name) / "aniflow"
        self.upstream = Path(self.tempdir.name) / "upstream"
        self._write(self.repo / "scripts" / "InstallVideoStudio.ps1", '$Version = "v7.0.4"\n')
        for asset in module.FIRST_EPISODE:
            self._write(self.repo / asset, "fake test asset\n")
        self._write(self.upstream / "core/api/agnes_video.py", "BusyTracker is_busy_signal ring.rotate() ring.next()\n")
        self._write(self.upstream / "core/api/retry_policy.py", "class BusyTracker: pass\ndef is_busy_signal(): pass\n")
        self._write(self.upstream / "core/api/key_manager.py", "def mark_auth_failed(): pass\n")
        self._write(self.upstream / "docs/public/usage.md", "AGNES_FIX_V25_PORTRAIT_ROTATION=1\n")

    def _write(self, path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_legacy_installer_remains_blocked_against_new_signatures(self) -> None:
        report = module.inspect(self.repo, self.upstream)
        self.assertEqual(report["repo"]["legacy_installer_pin"], "v7.0.4")
        self.assertFalse(report["repo"]["legacy_installer_matches_expected"])
        self.assertEqual(report["upstream"]["legacy_patch_anchors_present"], [False, False])
        self.assertEqual(report["result"], "REQUIRES_VERIFICATION")
        self.assertFalse(report["safe_to_apply_legacy_patch"])

    def test_new_pin_without_verified_identity_never_claims_live_success(self) -> None:
        self._write(self.repo / "scripts" / "InstallVideoStudio.ps1", '$Version = "v7.1.0"\n')
        report = module.inspect(self.repo, self.upstream)
        self.assertEqual(report["result"], "STATIC_SIGNATURES_MATCH_ONLY")
        self.assertFalse(report["upstream"]["release_identity_verified"])
        self.assertFalse(report["safe_to_claim_windows_or_video_verified"])

    def test_missing_upstream_is_not_success(self) -> None:
        report = module.inspect(self.repo)
        self.assertEqual(report["result"], "REQUIRES_VERIFICATION")
        self.assertFalse(report["upstream"]["supplied"])

    def test_missing_new_policy_is_blocked(self) -> None:
        (self.upstream / "core/api/retry_policy.py").unlink()
        report = module.inspect(self.repo, self.upstream)
        self.assertEqual(report["result"], "REQUIRES_VERIFICATION")
        self.assertFalse(report["upstream"]["source_files_present"]["retry_policy"])

    def test_old_patch_anchors_are_reported_but_not_applied(self) -> None:
        path = self.upstream / "core/api/agnes_video.py"
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(module.LEGACY_PATCH_ANCHORS))
        report = module.inspect(self.repo, self.upstream)
        self.assertEqual(report["upstream"]["legacy_patch_anchors_present"], [True, True])
        self.assertFalse(report["safe_to_apply_legacy_patch"])

    def test_does_not_read_env_or_modify_files(self) -> None:
        sensitive = self.repo / ".env"
        self._write(sensitive, "AGNES_API_KEY=SECRET_SENTINEL_NEVER_EXPORT\n")
        before = sensitive.read_bytes()
        report = module.inspect(self.repo, self.upstream)
        self.assertNotIn("SECRET_SENTINEL", str(report))
        self.assertEqual(before, sensitive.read_bytes())

    def test_incomplete_episode_is_blocked(self) -> None:
        (self.repo / module.FIRST_EPISODE[0]).unlink()
        report = module.inspect(self.repo, self.upstream)
        self.assertIn("First episode source assets are incomplete", report["blockers"])


if __name__ == "__main__":
    unittest.main()
