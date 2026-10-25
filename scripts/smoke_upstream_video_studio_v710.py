"""P0-009: verify upstream v7.1.0 can start on loopback without any API key.

This script starts ONLY a SHA-pinned, clean official checkout prepared in an
independent directory; it only makes local GET requests. It does not generate
videos, post jobs, configure keys or publish any service.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from prepare_video_studio_v710 import COMMIT, VERSION, SafetyError, verify_existing


class SmokeError(RuntimeError):
    """A server identity or safety requirement failed."""


def _response(url: str, *, timeout: float = 1.5) -> dict:
    """Bypass system proxies when calling the explicitly local service."""
    opener = build_opener(ProxyHandler({}))
    with opener.open(Request(url, method="GET"), timeout=timeout) as result:
        if result.status != 200:
            raise SmokeError("Unexpected local response status")
        if result.headers.get("Content-Length") and int(result.headers["Content-Length"]) > 1_000_000:
            raise SmokeError("Local response too large")
        raw = result.read(1_000_001)
    if len(raw) > 1_000_000:
        raise SmokeError("Local response too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise SmokeError("Local service returned invalid JSON") from None
    if not isinstance(data, dict):
        raise SmokeError("Local service JSON root is not an object")
    return data


def _health_matches(payload: dict) -> bool:
    return (
        payload.get("ok") is True
        and payload.get("service") == "agnes-video-generator"
        and payload.get("status") == "healthy"
    )


def _routes_match(payload: dict) -> bool:
    paths = payload.get("paths")
    return (
        isinstance(paths, dict)
        and "/api/health" in paths
        and "get" in paths["/api/health"]
        and "/api/tasks/simple" in paths
        and "post" in paths["/api/tasks/simple"]
    )


def _server_environment(parent_env: dict, port: int, workdir: Path) -> dict:
    """Remove inherited API and CI credentials from the subprocess environment."""
    if type(port) is not int or not 1024 <= port <= 65535:
        raise SmokeError("Port must be 1024..65535")
    env = dict(parent_env)
    prefixes = (
        "AGNES_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY", "GITHUB_TOKEN", "GH_TOKEN",
        "AWS_ACCESS_KEY", "AWS_SECRET", "AZURE_OPENAI_API_KEY",
    )
    for key in list(env):
        if key.upper().startswith(prefixes):
            env.pop(key)
    env.update({
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "AGNES_REGRESSION_WORKING_DIR": str(workdir),
        "AGNES_CORS_ENABLED": "false",
        "AGNES_CORS_ORIGINS": "",
        "AGNES_LOG_FILE": "",
        "AGNES_API_KEY": "",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost",
    })
    return env


def _check_isolated_upstream(upstream: Path) -> dict:
    upstream = Path(upstream)
    if upstream.is_symlink() or (upstream / ".env").exists() or (upstream / ".env").is_symlink():
        raise SmokeError("Checkout is a symlink or has local .env credentials")
    try:
        info = verify_existing(upstream)
    except SafetyError as exc:
        # Never echo full private paths or Git diagnostics.
        raise SmokeError(f"Pinned checkout verification failed ({type(exc).__name__})") from None
    if info["commit"] != COMMIT or info["release"] != VERSION:
        raise SmokeError("Official upstream release identity mismatch")
    return info


def run_smoke(upstream: Path, *, port: int = 18765, deadline_seconds: int = 75) -> dict:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise SmokeError("Port must be 1024..65535")
    if not 5 <= deadline_seconds <= 180:
        raise SmokeError("Startup deadline must be 5..180 seconds")
    identity = _check_isolated_upstream(upstream)
    upstream = Path(upstream).expanduser().resolve()
    # Detect a pre-existing service to avoid accidentally counting another app.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_port:
        test_port.settimeout(0.5)
        if test_port.connect_ex(("127.0.0.1", port)) == 0:
            raise SmokeError("Local port is already occupied")
    with tempfile.TemporaryDirectory(prefix="aniflow-v710-no-key-") as temp:
        workdir = Path(temp) / "working_dir"
        env = _server_environment(os.environ, port, workdir)
        proc = None
        try:
            proc = subprocess.Popen(
                [sys.executable, "-B", "server.py"],
                cwd=str(upstream),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            base = f"http://127.0.0.1:{port}"
            end = time.monotonic() + deadline_seconds
            while time.monotonic() < end:
                if proc.poll() is not None:
                    raise SmokeError(f"Native upstream service exited early ({proc.returncode})")
                try:
                    health = _response(base + "/api/health")
                    if not _health_matches(health):
                        raise SmokeError("Unexpected service identity on loopback port")
                    schema = _response(base + "/openapi.json")
                    if not _routes_match(schema):
                        raise SmokeError("Expected upstream routes are missing")
                    tasks = _response(base + "/api/tasks")
                    if tasks.get("tasks") != []:
                        raise SmokeError("Isolated startup unexpectedly contains tasks")
                    if proc.poll() is not None:
                        raise SmokeError("Native server stopped during health checks")
                    return {
                        "result": "PASS_UPSTREAM_NATIVE_LOOPBACK_NO_KEY",
                        "official_release": identity["release"],
                        "official_commit": identity["commit"],
                        "server_alive_at_health_check": True,
                        "health_service": health["service"],
                        "health_status": health["status"],
                        "creative_task_route_exists": "/api/tasks/creative" in schema["paths"],
                        "simple_task_route_exists": True,
                        "isolated_workdir": True,
                        "host": "127.0.0.1",
                        "port": port,
                        "api_keys_injected": False,
                        "video_create_requests": 0,
                        "task_count": 0,
                        "upstream_code_modified": False,
                        "video_generated": False,
                        "manual_windows_video_review_required": True,
                    }
                except (OSError, URLError, HTTPError, TimeoutError):
                    time.sleep(1)
            raise SmokeError("Native upstream service did not become healthy before deadline")
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=8)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--deadline-seconds", type=int, default=75)
    args = ap.parse_args(argv)
    try:
        result = run_smoke(args.upstream, port=args.port, deadline_seconds=args.deadline_seconds)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SmokeError, OSError) as exc:
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
