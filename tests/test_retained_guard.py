import importlib.util
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import botocore.session
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.validate import validate_parameters

EXPERIMENT = "aniflow-wan-ohio-20261027-retained-n"
INSTANCE_ID = "i-0123456789abcdef0"
START = datetime(2026, 10, 29, tzinfo=UTC)
EVENT = {"ExperimentId": EXPERIMENT, "StopUtc": "2026-10-29T00:05:00Z",
         "CleanupUtc": "2026-10-29T00:06:00Z"}


def module(name="retained_guard"):
    path = Path(__file__).parents[1] / f"infra/ec2/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Clock:
    def __init__(self, elapsed=300):
        self.elapsed = elapsed

    def monotonic(self):
        return self.elapsed

    def now(self):
        return START + timedelta(seconds=self.elapsed)

    def sleep(self, seconds):
        self.elapsed += seconds


class EC2:
    def __init__(self, states=("running",), phase="gpu-retained", experiment=EXPERIMENT,
                 region="us-east-2", clock=None):
        self.meta = SimpleNamespace(region_name=region)
        self.states = list(states)
        self.phase = phase
        self.experiment = experiment
        self.clock = clock
        self.calls = []

    def describe_instances(self, **request):
        self.calls.append(("describe", request))
        if self.clock:
            self.clock.sleep(8)
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        tags = [{"Key": "ExperimentId", "Value": self.experiment}]
        if self.phase is not None:
            tags.append({"Key": "ExperimentPhase", "Value": self.phase})
        return {"Reservations": [{"Instances": [{"InstanceId": INSTANCE_ID,
                "State": {"Name": state}, "Tags": tags}]}]}

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


@pytest.mark.parametrize("phase,state", [(None, "running"), ("gpu-preflight", "running"),
                                         (None, "stopped"), (None, "terminated")])
def test_missing_or_wrong_phase_never_mutates_or_claims_empty_success(phase, state):
    ec2 = EC2([state], phase=phase)
    with pytest.raises(RuntimeError, match="scope tags"):
        module().sweep(ec2, EXPERIMENT, True, True)
    assert [name for name, _ in ec2.calls] == ["describe"]
    assert ec2.calls[0][1]["Filters"] == [{"Name": "tag:ExperimentId", "Values": [EXPERIMENT]}]


def test_exact_experiment_is_checked_even_if_filter_returns_an_unowned_instance():
    ec2 = EC2(experiment="other")
    with pytest.raises(RuntimeError, match="scope tags"):
        module().sweep(ec2, EXPERIMENT, True, False)
    assert [name for name, _ in ec2.calls] == ["describe"]


@pytest.mark.parametrize("state", ["stopped", "terminated"])
@pytest.mark.parametrize("stop_due,cleanup_due", [(False, False), (True, False), (True, True)])
def test_stopped_and_terminated_instances_are_preserved_at_every_deadline(
        state, stop_due, cleanup_due):
    ec2 = EC2([state])
    result = module().sweep(ec2, EXPERIMENT, stop_due, cleanup_due)
    assert result["all_compute_stopped"] and result["all_compute_released"]
    assert result["matched_instances"] == 1
    assert [name for name, _ in ec2.calls] == ["describe"]


def test_stop_and_emergency_termination_force_skip_os_but_ack_is_not_completion():
    guard = module()
    ec2 = EC2(["running", "running", "terminated"])
    stop = guard.sweep(ec2, EXPERIMENT, True, False)
    assert not stop["all_compute_stopped"]
    assert ec2.calls[-1] == ("stop", {"InstanceIds": [INSTANCE_ID],
                                        "Force": True, "SkipOsShutdown": True})
    cleanup = guard.sweep(ec2, EXPERIMENT, True, True)
    assert not cleanup["all_compute_stopped"] and not cleanup["all_compute_released"]
    assert ec2.calls[-1] == ("terminate", {"InstanceIds": [INSTANCE_ID],
                                             "Force": True, "SkipOsShutdown": True})
    assert guard.sweep(ec2, EXPERIMENT, True, True)["all_compute_released"]
    model = botocore.session.get_session().get_service_model("ec2")
    for name, params in ec2.calls:
        if name != "describe":
            operation = "StopInstances" if name == "stop" else "TerminateInstances"
            validate_parameters(params, model.operation_model(operation).input_shape)


@pytest.mark.parametrize("state", ["pending", "running"])
def test_cleanup_terminates_only_pending_or_running_compute(state):
    ec2 = EC2([state])
    result = module().sweep(ec2, EXPERIMENT, True, True)
    assert not result["all_compute_stopped"] and not result["all_compute_released"]
    assert ec2.calls[-1] == ("terminate", {"InstanceIds": [INSTANCE_ID],
                                             "Force": True, "SkipOsShutdown": True})


def test_cleanup_retries_stop_for_stopping_but_never_claims_stopped_or_terminates():
    ec2 = EC2(["stopping"])
    result = module().sweep(ec2, EXPERIMENT, True, True)
    assert not result["all_compute_stopped"] and not result["all_compute_released"]
    assert result["states"] == ["stopping"]
    assert ec2.calls[-1] == ("stop", {"InstanceIds": [INSTANCE_ID],
                                        "Force": True, "SkipOsShutdown": True})
    assert not any(name == "terminate" for name, _ in ec2.calls)


def test_cleanup_only_observes_shutting_down_without_repeating_termination():
    ec2 = EC2(["shutting-down"])
    result = module().sweep(ec2, EXPERIMENT, True, True)
    assert not result["all_compute_stopped"] and not result["all_compute_released"]
    assert [name for name, _ in ec2.calls] == ["describe"]


@pytest.mark.parametrize("stop_due,cleanup_due", [(False, False), (True, False), (True, True)])
def test_unknown_state_is_rejected_before_any_mutation(stop_due, cleanup_due):
    ec2 = EC2(["unknown"])
    with pytest.raises(RuntimeError, match="Unknown instance state"):
        module().sweep(ec2, EXPERIMENT, stop_due, cleanup_due)
    assert [name for name, _ in ec2.calls] == ["describe"]


def test_mixed_inventory_unknown_state_blocks_mutation_of_all_instances():
    ec2 = EC2()
    describe = ec2.describe_instances

    def mixed(**request):
        response = describe(**request)
        unknown = dict(response["Reservations"][0]["Instances"][0])
        unknown["InstanceId"] = "i-00000000000000001"
        unknown["State"] = {"Name": "unknown"}
        response["Reservations"][0]["Instances"].append(unknown)
        return response

    ec2.describe_instances = mixed
    with pytest.raises(RuntimeError, match="Unknown instance state"):
        module().sweep(ec2, EXPERIMENT, True, True)
    assert [name for name, _ in ec2.calls] == ["describe"]


def test_before_deadlines_is_readonly_and_cleanup_cannot_precede_stop():
    ec2 = EC2()
    assert not module().sweep(ec2, EXPERIMENT, False, False)["all_compute_stopped"]
    assert [name for name, _ in ec2.calls] == ["describe"]
    with pytest.raises(RuntimeError, match="cannot precede"):
        module().sweep(ec2, EXPERIMENT, False, True)
    assert [name for name, _ in ec2.calls] == ["describe"]


def test_wrong_region_or_experiment_never_even_reads():
    for ec2, experiment in [(EC2(region="ap-northeast-1"), EXPERIMENT), (EC2(), "other")]:
        with pytest.raises(RuntimeError, match="Unexpected"):
            module().sweep(ec2, experiment, True, True)
        assert ec2.calls == []


def test_preflight_default_deadlines_are_five_and_six_minutes_with_conservative_rounding():
    guard = module()
    expected = {"stop_utc": EVENT["StopUtc"], "cleanup_utc": EVENT["CleanupUtc"]}
    assert guard.retained_deadlines(START) == expected
    assert guard.retained_deadlines(START.replace(microsecond=999999)) == expected
    for now in (START.replace(tzinfo=None), START.astimezone(timezone(timedelta(hours=8))), None):
        with pytest.raises(ValueError, match="aware UTC"):
            guard.retained_deadlines(now)


def test_api_client_is_one_bounded_attempt_and_checks_both_operation_models(monkeypatch):
    guard = module()
    client = Mock()
    client.meta.service_model = botocore.session.get_session().get_service_model("ec2")
    factory = Mock(return_value=client)
    monkeypatch.setattr(guard.boto3, "client", factory)
    assert guard.api() is client
    config = factory.call_args.kwargs["config"]
    assert config.connect_timeout == 3 and config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert guard.BACKUP_SECONDS == 480
    client.describe_instances.assert_not_called()
    client.stop_instances.assert_not_called()
    client.terminate_instances.assert_not_called()


@pytest.mark.parametrize("operation", ["StopInstances", "TerminateInstances"])
@pytest.mark.parametrize("missing", ["Force", "SkipOsShutdown"])
def test_legacy_sdk_is_rejected_before_any_ec2_request(monkeypatch, operation, missing):
    guard = module()
    client = Mock()

    def operation_model(name):
        fields = {"Force", "SkipOsShutdown"} - ({missing} if name == operation else set())
        return SimpleNamespace(input_shape=SimpleNamespace(members=dict.fromkeys(fields)))

    client.meta.service_model.operation_model.side_effect = operation_model
    monkeypatch.setattr(guard.boto3, "client", Mock(return_value=client))
    with pytest.raises(RuntimeError, match="EC2 SDK lacks Force/SkipOsShutdown support for "
                       + operation):
        guard.api()
    client.describe_instances.assert_not_called()
    client.stop_instances.assert_not_called()
    client.terminate_instances.assert_not_called()


@pytest.mark.parametrize("cleanup,state", [(False, "stopped"), (True, "stopped"),
                                          (True, "terminated")])
def test_independent_backup_preserves_observed_stopped_instance_without_mutation(
        monkeypatch, cleanup, state):
    guard = module()
    clock = Clock(360 if cleanup else 300)
    ec2 = EC2([state])
    monkeypatch.setattr(guard, "api", lambda: ec2)
    result = guard._backup(EVENT, cleanup, clock.now, clock.monotonic, clock.sleep)
    assert result["all_compute_released"]
    assert [name for name, _ in ec2.calls] == ["describe"]


@pytest.mark.parametrize("cleanup,states", [(False, ["running", "stopped"]),
                                           (True, ["running", "terminated"])])
def test_independent_backup_requires_later_terminal_observation(monkeypatch, cleanup, states):
    guard = module()
    clock = Clock(360 if cleanup else 300)
    ec2 = EC2(states)
    monkeypatch.setattr(guard, "api", lambda: ec2)
    result = guard._backup(EVENT, cleanup, clock.now, clock.monotonic, clock.sleep)
    assert result["all_compute_released"]
    writes = [(name, params) for name, params in ec2.calls if name != "describe"]
    assert writes == [("terminate" if cleanup else "stop", {
        "InstanceIds": [INSTANCE_ID], "Force": True, "SkipOsShutdown": True})]
    assert [name for name, _ in ec2.calls].count("describe") == 2


def test_independent_cleanup_preserves_instance_that_finishes_stopping_after_deadline(monkeypatch):
    guard = module()
    clock = Clock(360)
    ec2 = EC2(["stopping", "stopped"])
    monkeypatch.setattr(guard, "api", lambda: ec2)
    result = guard._backup(EVENT, True, clock.now, clock.monotonic, clock.sleep)
    assert result["all_compute_stopped"] and result["states"] == ["stopped"]
    assert [name for name, _ in ec2.calls] == ["describe", "stop", "describe"]


def test_independent_cleanup_waits_for_shutting_down_without_repeating_termination(monkeypatch):
    guard = module()
    clock = Clock(360)
    ec2 = EC2(["shutting-down", "terminated"])
    monkeypatch.setattr(guard, "api", lambda: ec2)
    result = guard._backup(EVENT, True, clock.now, clock.monotonic, clock.sleep)
    assert result["all_compute_stopped"] and result["states"] == ["terminated"]
    assert [name for name, _ in ec2.calls] == ["describe", "describe"]


@pytest.mark.parametrize("cleanup,seconds", [(False, 299), (True, 359)])
def test_backup_refuses_early_calls_before_constructing_client(monkeypatch, cleanup, seconds):
    guard = module()
    factory = Mock()
    monkeypatch.setattr(guard, "api", factory)
    clock = Clock(seconds)
    with pytest.raises(RuntimeError, match="before"):
        guard._backup(EVENT, cleanup, clock.now, clock.monotonic, clock.sleep)
    factory.assert_not_called()


def test_late_stop_is_readonly_and_does_not_delay_independent_cleanup(monkeypatch):
    guard = module()
    ec2 = EC2(["running"])
    monkeypatch.setattr(guard, "api", lambda: ec2)
    now = lambda: START + timedelta(minutes=6)
    with pytest.raises(RuntimeError, match="proceed to independent cleanup"):
        guard._backup(EVENT, False, now, lambda: 0, lambda seconds: pytest.fail("No delayed sleep"))
    assert [name for name, _ in ec2.calls] == ["describe"]


@pytest.mark.parametrize("cleanup,limit", [(False, 360), (True, 840)])
def test_unconfirmed_slow_calls_remain_bounded(monkeypatch, cleanup, limit):
    guard = module()
    clock = Clock(360 if cleanup else 300)
    ec2 = EC2(["stopping"], clock=clock)
    monkeypatch.setattr(guard, "api", lambda: ec2)
    with pytest.raises(RuntimeError, match="unconfirmed"):
        guard._backup(EVENT, cleanup, clock.now, clock.monotonic, clock.sleep)
    assert clock.elapsed <= limit
    assert not any(name == "terminate" for name, _ in ec2.calls)


def test_network_failure_has_same_bounded_retry_window(monkeypatch):
    guard = module()
    clock = Clock(360)
    ec2 = EC2()

    def offline(**request):
        clock.sleep(8)
        raise EndpointConnectionError(endpoint_url="https://example.invalid")

    ec2.describe_instances = offline
    monkeypatch.setattr(guard, "api", lambda: ec2)
    with pytest.raises(RuntimeError, match="unconfirmed"):
        guard._backup(EVENT, True, clock.now, clock.monotonic, clock.sleep)
    assert clock.elapsed <= 840


@pytest.mark.parametrize("cleanup", [False, True])
def test_backup_can_confirm_stopped_after_two_minutes_without_terminating(monkeypatch, cleanup):
    guard = module()
    event = {**EVENT, "CleanupUtc": "2026-10-29T00:15:00Z"}
    started = 900 if cleanup else 300
    clock = Clock(started)
    ec2 = EC2(["stopping"] * 7 + ["stopped"], clock=clock)
    monkeypatch.setattr(guard, "api", lambda: ec2)

    result = guard._backup(event, cleanup, clock.now, clock.monotonic, clock.sleep)

    assert result["all_compute_stopped"] and result["states"] == ["stopped"]
    assert started + 120 < clock.elapsed <= started + 480
    assert sum(name == "stop" for name, _ in ec2.calls) == 7
    assert not any(name == "terminate" for name, _ in ec2.calls)


def test_long_stop_confirmation_remains_bounded_by_eight_minutes(monkeypatch):
    guard = module()
    event = {**EVENT, "CleanupUtc": "2026-10-29T00:15:00Z"}
    clock = Clock(300)
    ec2 = EC2(["stopping"], clock=clock)
    monkeypatch.setattr(guard, "api", lambda: ec2)

    with pytest.raises(RuntimeError, match="unconfirmed"):
        guard._backup(event, False, clock.now, clock.monotonic, clock.sleep)

    assert 420 < clock.elapsed <= 780
    assert not any(name == "terminate" for name, _ in ec2.calls)


def test_long_stop_confirmation_still_yields_at_fixed_cleanup_deadline(monkeypatch):
    guard = module()
    event = {**EVENT, "CleanupUtc": "2026-10-29T00:07:30Z"}
    clock = Clock(300)
    ec2 = EC2(["stopping"], clock=clock)
    monkeypatch.setattr(guard, "api", lambda: ec2)

    with pytest.raises(RuntimeError, match="unconfirmed"):
        guard._backup(event, False, clock.now, clock.monotonic, clock.sleep)

    assert 420 < clock.elapsed <= 450
    assert not any(name == "terminate" for name, _ in ec2.calls)


def test_partial_pagination_cannot_prove_empty_success_or_mutate():
    guard = module()
    ec2 = EC2()
    ec2.describe_instances = Mock(return_value={"Reservations": [], "NextToken": "more"})
    with pytest.raises(RuntimeError, match="Partial instance observation"):
        guard.sweep(ec2, EXPERIMENT, True, True, single_page=True)
    assert ec2.calls == []


def test_templates_require_both_tags_and_keep_independent_execution_limits(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "infra/ec2"))
    primary, backup = module("retained_templates").templates()
    for template in (primary, backup):
        writes = template["Resources"]["Role"]["Properties"]["Policies"][0][
            "PolicyDocument"]["Statement"][1]
        assert set(writes["Action"]) == {"ec2:StopInstances", "ec2:TerminateInstances"}
        assert writes["Condition"]["StringEquals"] == {
            "aws:RequestedRegion": "us-east-2",
            "ec2:ResourceTag/ExperimentId": {"Ref": "ExperimentId"},
            "ec2:ResourceTag/ExperimentPhase": "gpu-retained"}
        for policy in template["Resources"]["Role"]["Properties"]["Policies"]:
            for statement in policy["PolicyDocument"]["Statement"]:
                actions = statement["Action"]
                actions = [actions] if isinstance(actions, str) else actions
                assert not {"ec2:RunInstances", "ec2:StartInstances"} & set(actions)
    props = primary["Resources"]["Guard"]["Properties"]
    source = props["Code"]["ZipFile"]
    assert props["Timeout"] == 25
    assert primary["Resources"]["Tick"]["Properties"]["Targets"][0][
        "RetryPolicy"]["MaximumRetryAttempts"] == 0
    assert primary["Resources"]["Invocation"]["Properties"]["MaximumRetryAttempts"] == 0
    assert 'PHASE = "gpu-retained"' in source
    assert "g7_guard" not in source and "preflight_guard" not in source
    steps = backup["Resources"]["Document"]["Properties"]["Content"]["mainSteps"]
    assert [s["name"] for s in steps] == [
        "WaitUntilStop", "IndependentStop", "WaitUntilCleanup", "IndependentCleanup"]
    assert steps[1]["onFailure"] == "Continue"
    for index in (1, 3):
        assert steps[index]["timeoutSeconds"] == 540 and steps[index]["maxAttempts"] == 1
        guard = module()
        assert guard.BACKUP_SECONDS + 2 * guard.API_SECONDS < steps[index]["timeoutSeconds"] <= 600
        assert steps[index]["inputs"]["Script"] == source
    base_steps = module("g7_templates").templates()[1]["Resources"]["Document"][
        "Properties"]["Content"]["mainSteps"]
    assert all(step["timeoutSeconds"] == 150 for step in base_steps
               if step["action"] == "aws:executeScript")
