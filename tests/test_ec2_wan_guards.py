import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

EXPERIMENT = "aniflow-wan-ohio-20261027-test"


def module(name="wan_guard"):
    path = Path(__file__).parents[1] / f"infra/ec2/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def client(state="running", owned=True, region="us-east-2"):
    ec2 = Mock()
    ec2.meta.region_name = region
    item = {"InstanceId": "i-test", "State": {"Name": state}, "Tags": [
        {"Key": "ExperimentId", "Value": EXPERIMENT if owned else EXPERIMENT + "-other"}]}
    ec2.get_paginator.return_value.paginate.return_value = [
        {"Reservations": [{"Instances": [item]}]}]
    return ec2


@pytest.mark.parametrize("region,experiment", [
    ("ap-northeast-1", EXPERIMENT), ("us-east-2", "another-experiment")])
def test_region_and_experiment_fail_closed_before_api_reads(region, experiment):
    ec2 = client(region=region)
    with pytest.raises(RuntimeError):
        module().sweep(ec2, experiment, True, True)
    assert not ec2.mock_calls


def test_api_filter_does_not_replace_exact_tag_check():
    ec2 = client(owned=False)
    result = module().sweep(ec2, EXPERIMENT, True, True)
    assert result["matched_instances"] == 0
    ec2.stop_instances.assert_not_called()
    ec2.terminate_instances.assert_not_called()


def test_before_deadline_only_reads():
    ec2 = client()
    module().sweep(ec2, EXPERIMENT, False, False)
    ec2.stop_instances.assert_not_called()
    ec2.terminate_instances.assert_not_called()


def test_stop_acknowledgement_is_not_proof_of_release():
    ec2 = client()
    ec2.stop_instances.return_value = {"StoppingInstances": [{"CurrentState": {"Name": "stopped"}}]}
    result = module().sweep(ec2, EXPERIMENT, True, False)
    ec2.stop_instances.assert_called_once_with(InstanceIds=["i-test"])
    assert result["states"] == ["running"] and not result["all_compute_released"]


@pytest.mark.parametrize("state", ["pending", "stopping", "stopped"])
def test_cleanup_terminates_pending_and_stopped_compute_without_claiming_completion(state):
    ec2 = client(state)
    result = module().sweep(ec2, EXPERIMENT, True, True)
    ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-test"])
    assert not result["all_compute_released"]


def test_stopped_instance_is_not_stopped_again_or_reported_terminated():
    ec2 = client("stopped")
    result = module().sweep(ec2, EXPERIMENT, True, False)
    ec2.stop_instances.assert_not_called()
    assert not result["all_compute_released"]


def test_termination_ack_requires_later_observation():
    guard = module()
    ec2 = client("running")
    assert not guard.sweep(ec2, EXPERIMENT, True, True)["all_compute_released"]
    terminated = client("terminated")
    result = guard.sweep(terminated, EXPERIMENT, True, True)
    terminated.terminate_instances.assert_not_called()
    assert result["all_compute_released"]
    assert "volumes" in result["scope"]


def test_absence_confirms_only_compute_scope():
    ec2 = client()
    ec2.get_paginator.return_value.paginate.return_value = []
    result = module().sweep(ec2, EXPERIMENT, True, True)
    assert result["all_compute_released"] and "not checked" in result["scope"]


@pytest.mark.parametrize("error", [EndpointConnectionError(endpoint_url="https://example.invalid"),
    ClientError({"Error": {"Code": "ThrottlingException"}}, "DescribeInstances")])
def test_backup_retries_network_and_service_failures(monkeypatch, error):
    guard = module()
    sweep = Mock(side_effect=[error, {"all_compute_released": True}])
    monkeypatch.setattr(guard, "sweep", sweep)
    monkeypatch.setattr(guard, "api", Mock())
    monkeypatch.setattr(guard.time, "sleep", Mock())
    assert guard.backup({"CleanupUtc": "2000-01-01T00:00:00Z", "ExperimentId": EXPERIMENT},
                        None)["all_compute_released"]
    assert sweep.call_count == 2


def test_backup_is_bounded_and_does_not_succeed_without_confirmation(monkeypatch):
    guard = module()
    monkeypatch.setattr(guard, "api", Mock())
    monkeypatch.setattr(guard, "sweep", Mock(return_value={"all_compute_released": False}))
    monkeypatch.setattr(guard.time, "monotonic", Mock(side_effect=[0, 0, 541]))
    monkeypatch.setattr(guard.time, "sleep", Mock())
    with pytest.raises(RuntimeError, match="unconfirmed"):
        guard.backup({"CleanupUtc": "2000-01-01T00:00:00Z", "ExperimentId": EXPERIMENT}, None)


def test_future_backup_cannot_terminate(monkeypatch):
    guard = module()
    api = Mock()
    monkeypatch.setattr(guard, "api", api)
    with pytest.raises(RuntimeError, match="before"):
        guard.backup({"CleanupUtc": "2999-01-01T00:00:00Z", "ExperimentId": EXPERIMENT}, None)
    api.assert_not_called()


def test_templates_allow_only_tagged_ohio_stop_and_terminate():
    for template in module("wan_templates").templates():
        policies = template["Resources"]["Role"]["Properties"]["Policies"]
        statements = policies[0]["PolicyDocument"]["Statement"]
        assert statements[0]["Action"] == "ec2:DescribeInstances"
        assert statements[0]["Condition"]["StringEquals"]["aws:RequestedRegion"] == "us-east-2"
        writes = statements[1]
        assert set(writes["Action"]) == {"ec2:StopInstances", "ec2:TerminateInstances"}
        assert writes["Resource"]["Fn::Sub"].endswith(":instance/*")
        assert ":us-east-2:" in writes["Resource"]["Fn::Sub"]
        assert writes["Condition"]["StringEquals"] == {
            "aws:RequestedRegion": "us-east-2",
            "ec2:ResourceTag/ExperimentId": {"Ref": "ExperimentId"}}
        assert not any(r["Type"].startswith("AWS::EC2::") for r in template["Resources"].values())


def test_primary_and_backup_have_independent_services_and_fixed_deadlines():
    primary, backup = module("wan_templates").templates()
    assert primary["Rules"]["GuardRegion"]["Assertions"][0]["Assert"]["Fn::Equals"][1] == "us-east-2"
    assert backup["Rules"]["GuardRegion"]["Assertions"][0]["Assert"]["Fn::Equals"][1] == "ap-southeast-1"
    assert primary["Resources"]["Tick"]["Properties"]["State"] == "ENABLED"
    serialized = json.dumps(backup)
    assert "lambda:InvokeFunction" not in serialized and "AWS::Lambda::Function" not in serialized
    steps = backup["Resources"]["Document"]["Properties"]["Content"]["mainSteps"]
    assert steps[0] == {"name": "WaitUntilCleanup", "action": "aws:sleep",
                        "inputs": {"Timestamp": {"Ref": "CleanupUtc"}}}
    assert len(steps[1:]) == 1
    assert steps[1]["maxAttempts"] == 3 and steps[1]["isEnd"] is True
    assert "onFailure" not in steps[1]
    assert all(s["action"] == "aws:executeScript" and s["timeoutSeconds"] == 600 for s in steps[1:])
    assert all("time.monotonic() + 540" in s["inputs"]["Script"] for s in steps[1:])
