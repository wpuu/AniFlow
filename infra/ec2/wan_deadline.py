"""Fail-closed per-boot EC2 shutdown using the fixed deadline in IMDSv2 user data."""

import re
import subprocess
import time
from datetime import UTC, datetime
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MARKER = "ANIFLOW_STOP_UTC"
DEADLINE_LINE = re.compile(
    r"# ANIFLOW_STOP_UTC=([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)")
IMDS = "http://169.254.169.254/latest/"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def read_user_data():
    # Bypass proxy environment variables; never request IAM credentials or execute user data.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    token_request = Request(IMDS + "api/token", method="PUT", headers={
        "X-aws-ec2-metadata-token-ttl-seconds": "60"})
    with opener.open(token_request, timeout=3) as response:
        token = response.read(4097).decode("ascii")
    if not token or len(token) > 4096 or "\r" in token or "\n" in token:
        raise ValueError("Invalid IMDSv2 token")
    data_request = Request(IMDS + "user-data", headers={"X-aws-ec2-metadata-token": token})
    with opener.open(data_request, timeout=3) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError("Oversized user data")
    return data.decode("utf-8")


def parse_deadline(user_data, now):
    lines = [line for line in user_data.splitlines() if MARKER in line]
    if len(lines) != 1 or not (match := DEADLINE_LINE.fullmatch(lines[0])):
        raise ValueError("User data must contain exactly one strict deadline line")
    deadline = datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if not 0 < (deadline - now).total_seconds() <= 4 * 60 * 60:
        raise ValueError("Deadline must be in the next four hours")
    return deadline


def shutdown():
    subprocess.run(["/sbin/shutdown", "-h", "now"], check=True, timeout=15)


def enforce_deadline(read=read_user_data, poweroff=shutdown,
                     now=lambda: datetime.now(UTC), monotonic=time.monotonic, sleep=time.sleep):
    try:
        # Reading once per process prevents a running instance's deadline from being extended.
        user_data = read()
        started = now()
        deadline = parse_deadline(user_data, started)
        monotonic_stop = monotonic() + (deadline - started).total_seconds()
        print("WAN_DEADLINE_ARMED:" + deadline.isoformat(), flush=True)
        while True:
            seconds = min((deadline - now()).total_seconds(), monotonic_stop - monotonic())
            if seconds <= 0:
                return
            # Recheck UTC so forward clock corrections cannot postpone the fixed deadline.
            sleep(min(30, seconds))
    finally:
        # Every failure, including IMDS and parsing failures, requests immediate shutdown.
        poweroff()


def main():
    try:
        enforce_deadline()
    except Exception as exc:  # noqa: BLE001 -- Do not print tokens, user data, or server errors.
        print("WAN_DEADLINE_STOPPED:" + type(exc).__name__, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
