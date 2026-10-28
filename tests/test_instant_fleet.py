import importlib.util
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import botocore.session
import pytest
from botocore.validate import validate_parameters

PATH = Path(__file__).parents[1] / "infra/ec2/instant_fleet.py"
SPEC = importlib.util.spec_from_file_location("instant_fleet", PATH)
FLEET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FLEET)
EXPERIMENT = "aniflow-wan-ohio-20261027-fleet-k"
FLEET_ID = "fleet-11111111-2222-3333-4444-555555555555"
INSTANCE_ID = "i-0123456789abcdef0"
SUBNETS = [{"SubnetId": "subnet-" + str(i) * 17, "AvailabilityZone": "us-east-2" + zone}
           for i, zone in enumerate("abc", start=1)]


def arguments():
    return {"template_id": "lt-0123456789abcdef0", "template_version": "1",
            "subnets": deepcopy(SUBNETS), "experiment_id": EXPERIMENT,
            "client_token": "persisted-unique-token",
            "valid_until": datetime(2026, 10, 28, 12, tzinfo=UTC)}


def row(kind="g6.xlarge", identifiers=None):
    return {"Lifecycle": "on-demand", "InstanceType": kind,
            "InstanceIds": [INSTANCE_ID] if identifiers is None else identifiers,
            "LaunchTemplateAndOverrides": {"Overrides": {"InstanceType": kind}}}


def error(code="InsufficientInstanceCapacity", kind="g5.xlarge"):
    return {"Lifecycle": "on-demand", "ErrorCode": code,
            "LaunchTemplateAndOverrides": {"Overrides": {"InstanceType": kind}}}


def response(instances=None, errors=None):
    return {"FleetId": FLEET_ID, "Instances": [] if instances is None else instances,
            "Errors": [] if errors is None else errors}


def test_request_has_only_six_approved_pools_and_one_on_demand_target():
    request = FLEET.build_request(**arguments())
    assert request["Type"] == "instant"
    assert request["TargetCapacitySpecification"] == {"TotalTargetCapacity": 1,
        "OnDemandTargetCapacity": 1, "SpotTargetCapacity": 0,
        "DefaultTargetCapacityType": "on-demand", "TargetCapacityUnitType": "units"}
    overrides = request["LaunchTemplateConfigs"][0]["Overrides"]
    assert len(overrides) == 6
    assert {(o["InstanceType"], o["SubnetId"]) for o in overrides} == {
        (kind, subnet["SubnetId"]) for kind in FLEET.ALLOWED_TYPES for subnet in SUBNETS}
    assert all(o["WeightedCapacity"] == 1 for o in overrides)
    assert [o["Priority"] for o in overrides] == [1, 1, 1, 2, 2, 2]
    assert request["OnDemandOptions"]["MaxTotalPrice"] == "1.006"
    assert {t["ResourceType"] for t in request["TagSpecifications"]} == {
        "fleet", "instance", "volume", "network-interface"}
    assert all({"Key": "ExperimentId", "Value": EXPERIMENT} in tags["Tags"]
               for tags in request["TagSpecifications"])
    model = botocore.session.get_session().get_service_model("ec2")
    validate_parameters(request, model.operation_model("CreateFleet").input_shape)


def test_instant_request_omits_unsupported_fleet_lifetime_even_with_valid_stop_deadline():
    request = FLEET.build_request(**arguments())
    assert "ValidUntil" not in request
    assert request["Type"] == "instant"
    assert "SpotOptions" not in request


@pytest.mark.parametrize("field,value", [
    ("template_id", "lt-other"), ("template_version", "$Latest"),
    ("template_version", "0"), ("template_version", True),
    ("experiment_id", "unrelated"), ("client_token", ""),
    ("client_token", "contains newline\n"),
    ("valid_until", datetime(2026, 10, 28)),
    ("valid_until", datetime(2026, 10, 28, tzinfo=timezone(timedelta(hours=8)))),
    ("valid_until", None),
    ("subnets", SUBNETS[:2]),
    ("subnets", [SUBNETS[0], SUBNETS[0], SUBNETS[2]]),
    ("subnets", [*SUBNETS[:2], {"SubnetId": "subnet-33333333333333333",
                               "AvailabilityZone": "us-east-1c"}]),
    ("subnets", [*SUBNETS[:2], None]),
])
def test_invalid_request_never_produces_launch_parameters(field, value):
    params = arguments()
    params[field] = value
    with pytest.raises(ValueError):
        FLEET.build_request(**params)


def test_success_and_other_pool_capacity_errors_preserve_the_created_instance():
    result = FLEET.classify_response(response([row()], [error()]))
    assert result == {"outcome": "created", "instance_ids": [INSTANCE_ID],
                      "error_codes": ["InsufficientInstanceCapacity"], "fleet_id": FLEET_ID}


@pytest.mark.parametrize("code", ["InsufficientCapacity", "InsufficientInstanceCapacity"])
def test_only_definitive_capacity_errors_with_no_instance_are_rejections(code):
    assert FLEET.classify_response(response(errors=[error(code)]))["outcome"] == "rejected"


@pytest.mark.parametrize("reply", [
    None, {}, response(), {"FleetState": "fulfilled", **response()},
    {"Instances": [row()], "Errors": []},
    response([row(identifiers=[INSTANCE_ID, INSTANCE_ID])]),
    response([row(), row("g5.xlarge", ["i-11111111111111111"])]),
    response([row("g6.2xlarge")]),
    response([row()], [error("AccessDenied")]),
    response(errors=[error("InvalidParameter")]),
    response(errors=[error(kind="g7.2xlarge")]),
    response([{"InstanceIds": [INSTANCE_ID]}]),
    response([row(identifiers=[INSTANCE_ID, None])]),
    response([row(identifiers=["not-an-instance-id"])]),
    response([None]), response(errors=[None]),
    response(errors=[{**error(), "ErrorCode": []}]),
    {"FleetId": FLEET_ID, "Instances": None, "Errors": []},
])
def test_ambiguous_and_out_of_scope_replies_require_reconciliation(reply):
    assert FLEET.classify_response(reply)["outcome"] == "reconcile_required"


def test_spot_or_missing_lifecycle_never_loses_the_instance_id():
    for lifecycle in (None, "spot"):
        instance = row()
        instance["Lifecycle"] = lifecycle
        result = FLEET.classify_response(response([instance]))
        assert result["outcome"] == "reconcile_required"
        assert result["instance_ids"] == [INSTANCE_ID]


def test_partial_response_with_multiple_instances_preserves_all_ids_and_errors():
    second = "i-11111111111111111"
    result = FLEET.classify_response(response([row(identifiers=[INSTANCE_ID, second])], [error()]))
    assert result["outcome"] == "reconcile_required"
    assert result["instance_ids"] == [INSTANCE_ID, second]
    assert result["error_codes"] == ["InsufficientInstanceCapacity"]
