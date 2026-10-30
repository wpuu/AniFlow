"""No test invokes a real shutdown or contacts instance metadata."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "wan_deadline", Path(__file__).parents[1] / "infra/ec2/wan_deadline.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
VALID = "# ANIFLOW_STOP_UTC=2026-10-27T13:00:00Z"


def test_unique_deadline_is_strict_utc_and_allows_crlf():
    assert guard.parse_deadline("#!/bin/bash\r\n" + VALID + "\r\n", NOW) == NOW + timedelta(hours=1)


@pytest.mark.parametrize("data", ["", "# no deadline", VALID + "\n" + VALID,
                                VALID + "\n# ANIFLOW_STOP_UTC=bad",
                                VALID + " ", " " + VALID, VALID.replace("Z", "+00:00"),
                                VALID.replace("10-27", "02-30"),
                                VALID.replace("13:00", "12:00"),
                                VALID.replace("13:00", "11:00"),
                                VALID.replace("13:00:00", "16:00:01"),
                                VALID + " && echo unexpected"])
def test_missing_duplicate_malformed_expired_and_overlong_deadlines_fail_closed(data):
    poweroff = Mock()
    with pytest.raises(ValueError):
        guard.enforce_deadline(read=lambda: data, poweroff=poweroff, now=lambda: NOW,
                               sleep=lambda _: pytest.fail("Invalid deadline slept"))
    poweroff.assert_called_once_with()


def test_four_hour_boundary():
    assert guard.parse_deadline(VALID.replace("13:00", "16:00"), NOW) == NOW + timedelta(hours=4)
    with pytest.raises(ValueError):
        guard.parse_deadline("# ANIFLOW_STOP_UTC=2026-10-27T16:00:01Z", NOW)


def test_imds_failure_immediately_requests_shutdown():
    poweroff = Mock()
    with pytest.raises(OSError):
        guard.enforce_deadline(read=Mock(side_effect=OSError("IMDS unavailable")),
                               poweroff=poweroff, sleep=lambda _: pytest.fail("IMDS failure slept"))
    poweroff.assert_called_once_with()


def test_deadline_cannot_extend_after_wall_clock_moves_backwards():
    elapsed = 0
    poweroff = Mock()
    read = Mock(return_value="# ANIFLOW_STOP_UTC=2026-10-27T12:01:00Z")
    intervals = []

    def sleep(seconds):
        nonlocal elapsed
        intervals.append(seconds)
        elapsed += seconds

    def now():
        return NOW + timedelta(seconds=elapsed - (3600 if elapsed else 0))

    guard.enforce_deadline(read=read, poweroff=poweroff, now=now,
                           monotonic=lambda: 100 + elapsed, sleep=sleep)
    assert elapsed == 60 and intervals == [30, 30]
    read.assert_called_once_with()
    poweroff.assert_called_once_with()


def test_forward_clock_move_triggers_shutdown_without_waiting_monotonic_budget():
    calls = 0
    elapsed = 0
    poweroff = Mock()

    def sleep(seconds):
        nonlocal elapsed
        elapsed += seconds

    def now():
        nonlocal calls
        calls += 1
        return NOW + timedelta(hours=2 if calls >= 3 else 0)

    guard.enforce_deadline(read=lambda: VALID, poweroff=poweroff, now=now,
                           monotonic=lambda: elapsed, sleep=sleep)
    assert elapsed == 30
    poweroff.assert_called_once_with()


def test_wait_failure_also_requests_shutdown():
    poweroff = Mock()
    with pytest.raises(RuntimeError):
        guard.enforce_deadline(read=lambda: VALID, poweroff=poweroff, now=lambda: NOW,
                               monotonic=lambda: 0, sleep=Mock(side_effect=RuntimeError("failed")))
    poweroff.assert_called_once_with()


def test_shutdown_is_a_fixed_argument_list_without_shell(monkeypatch):
    run = Mock()
    monkeypatch.setattr(guard.subprocess, "run", run)
    guard.shutdown()
    run.assert_called_once_with(["/sbin/shutdown", "-h", "now"], check=True, timeout=15)


def test_imds_uses_only_token_and_userdata_and_disables_proxies(monkeypatch):
    responses = [b"test-token", VALID.encode()]
    requests = []
    handlers = []

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return self.body[:limit]

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 3
            return Response(responses.pop(0))

    def build(*args):
        handlers.extend(args)
        return Opener()

    monkeypatch.setattr(guard, "build_opener", build)
    assert guard.read_user_data() == VALID
    assert isinstance(handlers[0], guard.ProxyHandler) and handlers[0].proxies == {}
    assert isinstance(handlers[1], guard.NoRedirect)
    assert [(request.get_method(), request.full_url) for request in requests] == [
        ("PUT", "http://169.254.169.254/latest/api/token"),
        ("GET", "http://169.254.169.254/latest/user-data")]
    assert requests[1].get_header("X-aws-ec2-metadata-token") == "test-token"


@pytest.mark.parametrize("token", [b"", b"bad\ntoken", b"x" * 4097])
def test_invalid_token_never_fetches_userdata(monkeypatch, token):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    response.read.return_value = token
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(guard, "build_opener", Mock(return_value=opener))
    with pytest.raises(ValueError):
        guard.read_user_data()
    assert opener.open.call_count == 1
