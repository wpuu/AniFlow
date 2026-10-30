import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import EndpointConnectionError

EXPERIMENT = "aniflow-wan-ohio-20261027-g7-h"
STOP = datetime(2026, 10, 28, tzinfo=UTC)
EVENT = {"ExperimentId": EXPERIMENT, "StopUtc": "2026-10-28T00:00:00Z",
         "CleanupUtc": "2026-10-28T00:01:00Z"}


def module(name="g7_guard"):
    path = Path(__file__).parents[1] / f"infra/ec2/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Clock:
    def __init__(self, elapsed=0):
        self.elapsed = elapsed

    def monotonic(self):
        return self.elapsed

    def now(self):
        return STOP + timedelta(seconds=self.elapsed)

    def sleep(self, seconds):
        self.elapsed += seconds


class EC2:
    def __init__(self, states=("running",), owned=True, region="us-east-2", clock=None):
        self.meta = SimpleNamespace(region_name=region)
        self.states = list(states)
        self.owned = owned
        self.clock = clock
        self.calls = []

    def describe_instances(self, **request):
        self.calls.append(("describe", request))
        if self.clock:
            self.clock.sleep(8)
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        item = {"InstanceId": "i-test", "State": {"Name": state}, "Tags": [
            {"Key": "ExperimentId", "Value": EXPERIMENT if self.owned else "other"}]}
        return {"Reservations": [{"Instances": [item]}]}

    def stop_instances(self, **request):
        self.calls.append(("stop", request))
        if self.clock:
            self.clock.sleep(8)
        return {"StoppingInstances": [{"CurrentState": {"Name": "stopped"}}]}

    def terminate_instances(self, **request):
        self.calls.append(("terminate", request))
        if self.clock:
            self.clock.sleep(8)
        return {"TerminatingInstances": [{"CurrentState": {"Name": "terminated"}}]}


@pytest.mark.parametrize("region,experiment", [
    ("us-east-1", EXPERIMENT), ("us-east-2", "unrelated")])
def test_wrong_scope_does_not_even_read(region, experiment):
    ec2 = EC2(region=region)
    with pytest.raises(RuntimeError, match="Unexpected"):
        module().sweep(ec2, experiment, True, True)
    assert ec2.calls == []


def test_exact_tags_are_checked_after_describe_filter():
    ec2 = EC2(owned=False)
    assert module().sweep(ec2, EXPERIMENT, True, True)["matched_instances"] == 0
    assert [call[0] for call in ec2.calls] == ["describe"]
    assert ec2.calls[0][1]["Filters"] == [{"Name": "tag:ExperimentId", "Values": [EXPERIMENT]}]


@pytest.mark.parametrize("state", ["pending", "stopping", "running", "shutting-down", "unknown"])
def test_transitional_unknown_and_acknowledged_states_are_not_completion(state):
    ec2 = EC2([state])
    result = module().sweep(ec2, EXPERIMENT, True, False)
    assert not result["all_compute_stopped"]
    assert not result["all_compute_released"]


@pytest.mark.parametrize("state,released", [("stopped", False), ("terminated", True)])
def test_only_observed_final_states_confirm_stop(state, released):
    result = module().sweep(EC2([state]), EXPERIMENT, True, False)
    assert result["all_compute_stopped"]
    assert result["all_compute_released"] is released


def test_force_stop_requires_stop_deadline():
    guard = module()
    ec2 = EC2(["stopping"])
    guard.sweep(ec2, EXPERIMENT, False, False)
    assert [call[0] for call in ec2.calls] == ["describe"]
    guard.sweep(ec2, EXPERIMENT, True, False)
    assert ec2.calls[-1] == ("stop", {"InstanceIds": ["i-test"], "Force": True})


def test_cleanup_uses_later_observation_and_never_infers_ack_completion():
    guard = module()
    ec2 = EC2(["stopped", "terminated"])
    assert not guard.sweep(ec2, EXPERIMENT, True, True)["all_compute_released"]
    assert ec2.calls[-1][0] == "terminate"
    assert guard.sweep(ec2, EXPERIMENT, True, True)["all_compute_released"]
    assert [call[0] for call in ec2.calls].count("terminate") == 1


@pytest.mark.parametrize("cleanup,seconds", [(False, -1), (True, 59)])
def test_backup_refuses_early_calls_without_api_creation(monkeypatch, cleanup, seconds):
    guard = module()
    api = Mock()
    monkeypatch.setattr(guard, "api", api)
    clock = Clock(seconds)
    with pytest.raises(RuntimeError, match="before"):
        guard._backup(EVENT, cleanup, clock.now, clock.monotonic, clock.sleep)
    api.assert_not_called()


@pytest.mark.parametrize("cleanup,states", [(False, ["pending", "stopping", "stopped"]),
                                            (True, ["stopped", "shutting-down", "terminated"])])
def test_backup_requires_real_final_observation(monkeypatch, cleanup, states):
    guard = module()
    clock = Clock(60 if cleanup else 0)
    ec2 = EC2(states)
    monkeypatch.setattr(guard, "api", lambda: ec2)
    result = guard._backup(EVENT, cleanup, clock.now, clock.monotonic, clock.sleep)
    assert result["all_compute_released" if cleanup else "all_compute_stopped"]
    assert [call[0] for call in ec2.calls].count("describe") == 3


@pytest.mark.parametrize("cleanup,limit", [(False, 60), (True, 180)])
def test_backup_loop_is_bounded_even_with_slow_api_and_unconfirmed_states(monkeypatch, cleanup, limit):
    guard = module()
    clock = Clock(60 if cleanup else 0)
    ec2 = EC2(["stopping"], clock=clock)
    monkeypatch.setattr(guard, "api", lambda: ec2)
    with pytest.raises(RuntimeError, match="unconfirmed"):
        guard._backup(EVENT, cleanup, clock.now, clock.monotonic, clock.sleep)
    assert clock.elapsed <= limit
    if not cleanup:
        assert not any(call[0] == "terminate" for call in ec2.calls)


def test_pagination_cannot_exhaust_backup_budget_or_claim_partial_release():
    guard = module()
    clock = Clock()
    ec2 = EC2()

    def continuing(**request):
        clock.sleep(8)
        return {"Reservations": [], "NextToken": "another-page"}

    ec2.describe_instances = continuing
    with pytest.raises(RuntimeError, match="Insufficient time"):
        guard.sweep(ec2, EXPERIMENT, True, True, until=120, monotonic=clock.monotonic)
    assert clock.elapsed == 112
    assert ec2.calls == []


@pytest.mark.parametrize("handler,cleanup", [("backup_stop", False), ("backup_cleanup", True)])
def test_independent_entry_points_select_only_their_own_operation(monkeypatch, handler, cleanup):
    guard = module()
    backup = Mock(return_value={"confirmed": True})
    monkeypatch.setattr(guard, "_backup", backup)
    assert getattr(guard, handler)(EVENT, None) == {"confirmed": True}
    backup.assert_called_once_with(EVENT, cleanup)


def test_network_failure_retry_has_same_120_second_bound(monkeypatch):
    guard = module()
    clock = Clock(60)
    ec2 = EC2()

    def offline(**request):
        clock.sleep(8)
        raise EndpointConnectionError(endpoint_url="https://example.invalid")

    ec2.describe_instances = offline
    monkeypatch.setattr(guard, "api", lambda: ec2)
    with pytest.raises(RuntimeError, match="unconfirmed"):
        guard._backup(EVENT, True, clock.now, clock.monotonic, clock.sleep)
    assert 68 <= clock.elapsed <= 180


def test_past_cleanup_stop_can_confirm_zero_targets_with_one_read(monkeypatch):
    guard = module()
    clock = Clock(61)
    ec2 = EC2()
    ec2.describe_instances = Mock(return_value={"Reservations": []})
    monkeypatch.setattr(guard, "api", lambda: ec2)
    result = guard._backup(EVENT, False, clock.now, clock.monotonic, clock.sleep)
    assert result["all_compute_stopped"] and result["matched_instances"] == 0
    assert ec2.describe_instances.call_count == 1
    assert ec2.calls == [] and clock.elapsed == 61


@pytest.mark.parametrize("state", ["pending", "running", "stopping", "unknown"])
def test_past_cleanup_stop_fails_active_targets_without_any_mutation(monkeypatch, state):
    guard = module()
    clock = Clock(61)
    ec2 = EC2([state])
    monkeypatch.setattr(guard, "api", lambda: ec2)
    with pytest.raises(RuntimeError, match="Late stop final state is unconfirmed"):
        guard._backup(EVENT, False, clock.now, clock.monotonic, clock.sleep)
    assert [call[0] for call in ec2.calls] == ["describe"]
    assert clock.elapsed == 61


@pytest.mark.parametrize("state", ["stopped", "terminated"])
def test_past_cleanup_stop_can_confirm_observed_final_state(monkeypatch, state):
    guard = module()
    clock = Clock(60)
    ec2 = EC2([state])
    monkeypatch.setattr(guard, "api", lambda: ec2)
    assert guard._backup(EVENT, False, clock.now, clock.monotonic, clock.sleep)[
        "all_compute_stopped"]
    assert [call[0] for call in ec2.calls] == ["describe"]


def test_past_cleanup_stop_fails_unknown_additional_pages_without_following_them(monkeypatch):
    guard = module()
    clock = Clock(61)
    ec2 = EC2()
    ec2.describe_instances = Mock(return_value={"Reservations": [], "NextToken": "more"})
    monkeypatch.setattr(guard, "api", lambda: ec2)
    with pytest.raises(RuntimeError, match="Partial instance observation"):
        guard._backup(EVENT, False, clock.now, clock.monotonic, clock.sleep)
    assert ec2.describe_instances.call_count == 1
    assert ec2.calls == [] and clock.elapsed == 61


def test_client_has_one_bounded_attempt(monkeypatch):
    guard = module()
    client = Mock()
    monkeypatch.setattr(guard.boto3, "client", client)
    guard.api()
    config = client.call_args.kwargs["config"]
    assert config.connect_timeout == 3 and config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert client.call_args.kwargs["region_name"] == "us-east-2"


@pytest.mark.parametrize("seconds,expected", [(-1, []), (0, ["stop"]), (59, ["stop"]),
                                              (60, ["terminate"])])
def test_primary_uses_both_absolute_deadlines(monkeypatch, seconds, expected):
    guard = module()
    ec2 = EC2()
    monkeypatch.setattr(guard, "api", lambda: ec2)
    monkeypatch.setenv("EXPERIMENT_ID", EXPERIMENT)
    monkeypatch.setenv("STOP_UTC", EVENT["StopUtc"])
    monkeypatch.setenv("CLEANUP_UTC", EVENT["CleanupUtc"])
    monkeypatch.setattr(guard, "datetime", SimpleNamespace(
        now=lambda zone: STOP + timedelta(seconds=seconds), strptime=datetime.strptime))
    guard.handler({}, None)
    assert [call[0] for call in ec2.calls if call[0] != "describe"] == expected


def test_templates_preserve_scope_and_bound_retries_and_both_deadlines(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "infra/ec2"))
    primary, backup = module("g7_templates").templates()
    for template in (primary, backup):
        writes = template["Resources"]["Role"]["Properties"]["Policies"][0][
            "PolicyDocument"]["Statement"][1]
        assert set(writes["Action"]) == {"ec2:StopInstances", "ec2:TerminateInstances"}
        assert writes["Condition"]["StringEquals"] == {
            "aws:RequestedRegion": "us-east-2",
            "ec2:ResourceTag/ExperimentId": {"Ref": "ExperimentId"}}
        assert template["Parameters"]["StopUtc"] == primary["Parameters"]["StopUtc"]
    assert primary["Resources"]["Guard"]["Properties"]["Timeout"] == 25
    assert primary["Resources"]["Tick"]["Properties"]["Targets"][0][
        "RetryPolicy"]["MaximumRetryAttempts"] == 0
    invoke = primary["Resources"]["Invocation"]["Properties"]
    assert invoke["MaximumRetryAttempts"] == 0 and invoke["MaximumEventAgeInSeconds"] == 60
    assert invoke["Qualifier"] == "$LATEST"
    environment = primary["Resources"]["Guard"]["Properties"]["Environment"]["Variables"]
    assert environment["STOP_UTC"] == {"Ref": "StopUtc"}
    assert environment["CLEANUP_UTC"] == {"Ref": "CleanupUtc"}
    steps = backup["Resources"]["Document"]["Properties"]["Content"]["mainSteps"]
    assert [step["name"] for step in steps] == [
        "WaitUntilStop", "IndependentStop", "WaitUntilCleanup", "IndependentCleanup"]
    assert steps[0]["inputs"]["Timestamp"] == {"Ref": "StopUtc"}
    assert steps[2]["inputs"]["Timestamp"] == {"Ref": "CleanupUtc"}
    assert steps[1]["onFailure"] == "Continue" and not steps[1].get("isEnd", False)
    assert steps[3]["isEnd"] is True
    source = primary["Resources"]["Guard"]["Properties"]["Code"]["ZipFile"]
    for step, handler in [(steps[1], "backup_stop"), (steps[3], "backup_cleanup")]:
        assert step["timeoutSeconds"] == 150 and step["maxAttempts"] == 1
        assert step["inputs"]["Handler"] == handler
        assert step["inputs"]["Script"] == source
        assert step["inputs"]["InputPayload"] == {
            "ExperimentId": {"Ref": "ExperimentId"},
            "StopUtc": {"Ref": "StopUtc"}, "CleanupUtc": {"Ref": "CleanupUtc"}}
    assert "wan_guard" not in source and "g7_guard" not in source
    assert "lambda:InvokeFunction" not in json.dumps(backup)
    assert backup["Rules"]["GuardRegion"]["Assertions"][0]["Assert"]["Fn::Equals"][1] == (
        "ap-southeast-1")
