"""P0-009 offline tests for the no-key native-upstream boot guard.

No real Agnes service, credentials, or video-generation requests are involved.
"""
from __future__ import annotations

import importlib.util
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/smoke_upstream_video_studio_v710.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("aniflow_upstream_smoke", SCRIPT)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class NativeUpstreamSmokeGuards(unittest.TestCase):
    def test_correct_health_payload_is_required(self):
        self.assertTrue(smoke._health_matches(
            {"ok": True, "service": "agnes-video-generator", "status": "healthy"}
        ))
        self.assertFalse(smoke._health_matches(
            {"ok": True, "service": "another-service", "status": "healthy"}
        ))

    def test_false_positive_boolean_values_do_not_count(self):
        self.assertFalse(smoke._health_matches(
            {"ok": "true", "service": "agnes-video-generator", "status": "healthy"}
        ))

    def test_actual_openapi_routes_must_be_present(self):
        self.assertTrue(smoke._routes_match({
            "paths": {
                "/api/health": {"get": {}},
                "/api/tasks/simple": {"post": {}},
            }
        }))
        self.assertFalse(smoke._routes_match({"paths": {"/api/health": {"get": {}}}}))

    def test_remove_secret_keys_and_force_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            environ = {
                "PATH": "safe", "AGNES_API_KEY": "DO_NOT_LEAK",
                "AGNES_API_KEY_2": "DO_NOT_LEAK",
                "OPENAI_API_KEY": "DO_NOT_LEAK",
                "GITHUB_TOKEN": "DO_NOT_LEAK",
                "AWS_SECRET_ACCESS_KEY": "DO_NOT_LEAK",
                "HOST": "0.0.0.0",
                "PORT": "8765",
            }
            clean = smoke._server_environment(environ, 18765, Path(tmp))
            self.assertEqual(clean["HOST"], "127.0.0.1")
            self.assertEqual(clean["PORT"], "18765")
            self.assertEqual(clean["PATH"], "safe")
            self.assertEqual(clean["AGNES_API_KEY"], "")
            self.assertNotIn("AGNES_API_KEY_2", clean)
            self.assertNotIn("OPENAI_API_KEY", clean)
            self.assertNotIn("GITHUB_TOKEN", clean)
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", clean)
            self.assertEqual(clean["AGNES_CORS_ENABLED"], "false")
            self.assertEqual(clean["HTTPS_PROXY"], "http://127.0.0.1:9")

    def test_port_must_be_valid_without_touching_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(smoke.SmokeError):
                smoke._server_environment({}, 80, Path(tmp))
            with self.assertRaises(smoke.SmokeError):
                smoke._server_environment({}, True, Path(tmp))

    def test_checkout_with_dot_env_is_blocked_before_git_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("AGNES_API_KEY=DO_NOT_PRINT", encoding="utf-8")
            with (
                patch.object(smoke, "verify_existing") as verify,
                self.assertRaisesRegex(smoke.SmokeError, "credentials"),
            ):
                smoke._check_isolated_upstream(root)
            verify.assert_not_called()

    def test_wrong_upstream_commit_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = {"commit": "0" * 40, "release": smoke.VERSION}
            with (
                patch.object(smoke, "verify_existing", return_value=info),
                self.assertRaisesRegex(smoke.SmokeError, "identity mismatch"),
            ):
                smoke._check_isolated_upstream(Path(tmp))

    def test_missing_pinned_checkout_does_not_expose_git_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(
                    smoke, "verify_existing",
                    side_effect=smoke.SafetyError("hidden local path/private diagnostic")
                ),
                self.assertRaises(smoke.SmokeError) as caught,
            ):
                smoke._check_isolated_upstream(Path(tmp))
            self.assertNotIn("hidden local path", str(caught.exception))

    def test_occupied_loopback_port_fails_without_launch(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener,
        ):
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            with (
                patch.object(smoke, "_check_isolated_upstream", return_value={
                    "release": smoke.VERSION, "commit": smoke.COMMIT
                }),
                patch.object(smoke.subprocess, "Popen") as launcher,
                self.assertRaisesRegex(smoke.SmokeError, "occupied"),
            ):
                smoke.run_smoke(Path(tmp), port=port)
            launcher.assert_not_called()

    def test_smoke_deadline_limits_are_strict(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            self.assertRaisesRegex(smoke.SmokeError, "Startup deadline"),
        ):
            smoke.run_smoke(Path(tmp), deadline_seconds=1)


if __name__ == "__main__":
    unittest.main()
