import importlib.util
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import botocore.session
import pytest
from botocore.validate import validate_parameters

EXPERIMENT = "aniflow-wan-ohio-20261027-preflight-draft"
INSTANCE_ID = "i-0123456789abcdef0"
START = datetime(2026, 10, 28, 14, tzinfo=UTC)
EVENT = {"ExperimentId": EXPERIMENT, "StopUtc": "2026-10-28T14:05:00Z",
         "CleanupUtc": "2026-10-28T14:06:00Z"}


def module(name="preflight_guard"):
    path = Path(__file__).parents[1] / f"infra/ec2/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class EC2:
    def __init__(self, states=("running",), phase="gpu-preflight", experiment=EXPERIMENT,
                 region="us-east-2"):
        self.meta = SimpleNamespace(region_name=region)
        self.states = list(states)
        self.phase = phase
        self.experiment = experiment
        self.calls = []

    def describe_instances(self, **request):
        self.calls.append(("describe", request))
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        tags = [{"Key": "ExperimentId", "Value": self.experiment}]
        if self.phase is not None:
            tags.append({"Key": "ExperimentPhase", "Value": self.phase})
        return {"Reservations": [{"Instances": [{"InstanceId": INSTANCE_ID,
                "State": {"Name": state}, "Tags": tags}]}]}

    def stop_instances(self, **request):
        self.calls.append(("stop", request))
        return {"StoppingInstances": [{"CurrentState": {"Name": "stopped"}}]}

    def terminate_instances(self, **request):
        self.calls.append(("terminate", request))
        return {"TerminatingInstances": [{"CurrentState": {"Name": "terminated"}}]}


@pytest.mark.parametrize("phase,state", [(None, "running"), ("models", "running"),
                                         (None, "terminated")])
def test_missing_or_wrong_phase_never_mutates_or_claims_empty_success(phase, state):
    ec2 = EC2([state], phase=phase)
    with pytest.raises(RuntimeError, match="scope tags"):
        module().sweep(ec2, EXPERIMENT, True, True)
    assert [name for name, _ in ec2.calls] == ["describe"]
    assert ec2.calls[0][1]["Filters"] == [{"Name": "tag:ExperimentId", "Values": [EXPERIMENT]}]


def test_exact_experiment_is_checked_even_if_api_filter_returns_an_unowned_instance():
    ec2 = EC2(experiment="other")
    with pytest.raises(RuntimeError, match="scope tags"):
        module().sweep(ec2, EXPERIMENT, True, False)
    assert [name for name, _ in ec2.calls] == ["describe"]


def test_both_shutdown_operations_force_and_skip_os_and_ack_is_not_completion():
    guard = module()
    ec2 = EC2(["running", "stopped", "terminated"])
    stop = guard.sweep(ec2, EXPERIMENT, True, False)
    assert not stop["all_compute_stopped"]
    assert ec2.calls[-1] == ("stop", {"InstanceIds": [INSTANCE_ID],
                                        "Force": True, "SkipOsShutdown": True})
    terminate = guard.sweep(ec2, EXPERIMENT, True, True)
    assert terminate["all_compute_stopped"] and not terminate["all_compute_released"]
    assert ec2.calls[-1] == ("terminate", {"InstanceIds": [INSTANCE_ID],
                                             "Force": True, "SkipOsShutdown": True})
    assert guard.sweep(ec2, EXPERIMENT, True, True)["all_compute_released"]
    model = botocore.session.get_session().get_service_model("ec2")
    for name, params in ec2.calls:
        if name != "describe":
            operation = "StopInstances" if name == "stop" else "TerminateInstances"
            validate_parameters(params, model.operation_model(operation).input_shape)


@pytest.mark.parametrize("state", ["pending", "stopping", "shutting-down"])
def test_transitional_states_never_prove_real_stop_or_release(state):
    result = module().sweep(EC2([state]), EXPERIMENT, True, True)
    assert not result["all_compute_stopped"] and not result["all_compute_released"]


def test_wrong_region_or_experiment_never_even_reads():
    for ec2, experiment in [(EC2(region="ap-northeast-1"), EXPERIMENT), (EC2(), "other")]:
        with pytest.raises(RuntimeError, match="Unexpected"):
            module().sweep(ec2, experiment, True, True)
        assert ec2.calls == []


def test_fresh_deadlines_are_five_and_six_minutes_with_conservative_rounding():
    guard = module()
    assert guard.preflight_deadlines(START) == {
        "stop_utc": EVENT["StopUtc"], "cleanup_utc": EVENT["CleanupUtc"]}
    assert guard.preflight_deadlines(START.replace(microsecond=999999)) == guard.preflight_deadlines(START)
    for now in (START.replace(tzinfo=None), START.astimezone(timezone(timedelta(hours=8))), None):
        with pytest.raises(ValueError, match="aware UTC"):
            guard.preflight_deadlines(now)


def test_api_client_is_still_one_bounded_attempt(monkeypatch):
    guard = module()
    client = Mock()
    client.return_value.meta.service_model = botocore.session.get_session().get_service_model("ec2")
    monkeypatch.setattr(guard.boto3, "client", client)
    guard.api()
    config = client.call_args.kwargs["config"]
    assert config.connect_timeout == 3 and config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert guard.BACKUP_SECONDS == 120


def test_api_accepts_complete_cloud_sdk_metadata_without_any_ec2_request(monkeypatch):
    guard = module()
    client = Mock()
    client.meta.service_model.operation_model.return_value = SimpleNamespace(
        input_shape=SimpleNamespace(members={"Force": object(), "SkipOsShutdown": object()}))
    factory = Mock(return_value=client)
    monkeypatch.setattr(guard.boto3, "client", factory)
    assert guard.api() is client
    assert [call.args[0] for call in client.meta.service_model.operation_model.call_args_list] == [
        "StopInstances", "TerminateInstances"]
    client.describe_instances.assert_not_called()
    client.stop_instances.assert_not_called()
    client.terminate_instances.assert_not_called()
    assert factory.call_count == 1


def test_api_refuses_either_legacy_operation_model_before_any_ec2_request(monkeypatch):
    guard = module()
    for operation in ("StopInstances", "TerminateInstances"):
        for missing in ("Force", "SkipOsShutdown"):
            client = Mock()

            def operation_model(name, missing=missing, operation=operation):
                fields = {"Force", "SkipOsShutdown"} - ({missing} if name == operation else set())
                return SimpleNamespace(input_shape=SimpleNamespace(members=dict.fromkeys(fields)))

            client.meta.service_model.operation_model.side_effect = operation_model
            factory = Mock(return_value=client)
            monkeypatch.setattr(guard.boto3, "client", factory)
            with pytest.raises(RuntimeError, match="EC2 SDK lacks Force/SkipOsShutdown support for "
                               + operation):
                guard.api()
            client.describe_instances.assert_not_called()
            client.stop_instances.assert_not_called()
            client.terminate_instances.assert_not_called()
            assert factory.call_count == 1


@pytest.mark.parametrize("cleanup,states", [(False, ["running", "stopped"]),
                                           (True, ["stopped", "terminated"])])
def test_independent_backup_forces_only_its_phase_and_requires_later_terminal_observation(
        monkeypatch, cleanup, states):
    guard = module()
    ec2 = EC2(states)
    monkeypatch.setattr(guard, "api", lambda: ec2)
    elapsed = 360 if cleanup else 300

    def sleep(seconds):
        nonlocal elapsed
        elapsed += seconds

    result = guard._backup(EVENT, cleanup, lambda: START + timedelta(seconds=elapsed),
                           lambda: elapsed, sleep)
    assert result["all_compute_released" if cleanup else "all_compute_stopped"]
    writes = [(name, params) for name, params in ec2.calls if name != "describe"]
    assert writes == [("terminate" if cleanup else "stop", {
        "InstanceIds": [INSTANCE_ID], "Force": True, "SkipOsShutdown": True})]
    assert [name for name, _ in ec2.calls].count("describe") == 2


def test_late_stop_is_readonly_and_does_not_delay_independent_cleanup(monkeypatch):
    guard = module()
    ec2 = EC2(["running"])
    monkeypatch.setattr(guard, "api", lambda: ec2)
    now = lambda: START + timedelta(minutes=6)
    with pytest.raises(RuntimeError, match="proceed to independent cleanup"):
        guard._backup(EVENT, False, now, lambda: 0, lambda seconds: pytest.fail("No delayed sleep"))
    assert [name for name, _ in ec2.calls] == ["describe"]


def test_draft_templates_keep_independent_limits_and_require_both_resource_tags(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "infra/ec2"))
    primary, backup = module("preflight_templates").templates()
    for template in (primary, backup):
        writes = template["Resources"]["Role"]["Properties"]["Policies"][0][
            "PolicyDocument"]["Statement"][1]
        assert set(writes["Action"]) == {"ec2:StopInstances", "ec2:TerminateInstances"}
        assert writes["Condition"]["StringEquals"] == {
            "aws:RequestedRegion": "us-east-2",
            "ec2:ResourceTag/ExperimentId": {"Ref": "ExperimentId"},
            "ec2:ResourceTag/ExperimentPhase": "gpu-preflight"}
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
    assert 'PHASE = "gpu-preflight"' in source
    assert "g7_guard" not in source and "preflight_guard" not in source
    steps = backup["Resources"]["Document"]["Properties"]["Content"]["mainSteps"]
    assert [s["name"] for s in steps] == [
        "WaitUntilStop", "IndependentStop", "WaitUntilCleanup", "IndependentCleanup"]
    assert steps[1]["onFailure"] == "Continue"
    for index in (1, 3):
        assert steps[index]["timeoutSeconds"] == 150 and steps[index]["maxAttempts"] == 1
        assert steps[index]["inputs"]["Script"] == source
