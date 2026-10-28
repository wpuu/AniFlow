"""Pure request and response checks for one bounded Ohio On-Demand GPU admission."""
import re
from datetime import datetime, timedelta

ALLOWED_TYPES = ("g6.xlarge", "g5.xlarge")
ZONES = {"us-east-2a", "us-east-2b", "us-east-2c"}
CAPACITY_ERRORS = {"InsufficientInstanceCapacity", "InsufficientCapacity"}
EXPERIMENT = re.compile(r"aniflow-wan-ohio-20261027-[a-z0-9-]+")
INSTANCE_ID = re.compile(r"i-(?:[0-9a-f]{8}|[0-9a-f]{17})")
FLEET_ID = re.compile(r"fleet-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def build_request(template_id, template_version, subnets, experiment_id, client_token, valid_until):
    """Build exactly six candidates for one instance; the caller verifies live protection first."""
    if not isinstance(template_id, str) or not re.fullmatch(r"lt-[0-9a-f]{8,17}", template_id):
        raise ValueError("A concrete launch template ID is required")
    version = str(template_version)
    if not re.fullmatch(r"[1-9][0-9]*", version):
        raise ValueError("A fixed positive launch template version is required")
    if not isinstance(experiment_id, str) or not EXPERIMENT.fullmatch(experiment_id):
        raise ValueError("Unexpected experiment scope")
    if not isinstance(client_token, str) or not re.fullmatch(r"[\x21-\x7e]{1,64}", client_token):
        raise ValueError("A persisted printable client token is required")
    if not isinstance(valid_until, datetime) or valid_until.utcoffset() != timedelta(0):
        raise ValueError("The immutable stop deadline must be an aware UTC datetime")
    if not isinstance(subnets, (list, tuple)) or len(subnets) != 3:
        raise ValueError("Exactly three Ohio subnets are required")
    if any(not isinstance(s, dict) for s in subnets):
        raise ValueError("Subnet observations must be mappings")
    zones = [s.get("AvailabilityZone") for s in subnets]
    identifiers = [s.get("SubnetId") for s in subnets]
    if any(not isinstance(z, str) for z in zones) or set(zones) != ZONES:
        raise ValueError("The candidates must cover Ohio 2a, 2b and 2c exactly once")
    if any(not isinstance(s, str) or not re.fullmatch(r"subnet-[0-9a-f]{8,17}", s)
           for s in identifiers) or len(set(identifiers)) != 3:
        raise ValueError("Three distinct concrete subnet IDs are required")
    overrides = [{"InstanceType": kind, "SubnetId": subnet["SubnetId"],
                  "WeightedCapacity": 1, "Priority": priority}
                 for priority, kind in enumerate(ALLOWED_TYPES, start=1)
                 for subnet in sorted(subnets, key=lambda item: item["AvailabilityZone"])]
    return {"Type": "instant", "ClientToken": client_token, "ValidUntil": valid_until,
        "OnDemandOptions": {"AllocationStrategy": "prioritized", "MaxTotalPrice": "1.006",
                            "SingleInstanceType": True, "MinTargetCapacity": 1},
        "TargetCapacitySpecification": {"TotalTargetCapacity": 1, "OnDemandTargetCapacity": 1,
            "SpotTargetCapacity": 0, "DefaultTargetCapacityType": "on-demand",
            "TargetCapacityUnitType": "units"},
        "LaunchTemplateConfigs": [{"LaunchTemplateSpecification": {
            "LaunchTemplateId": template_id, "Version": version}, "Overrides": overrides}],
        "TagSpecifications": [{"ResourceType": kind, "Tags": [
            {"Key": "ExperimentId", "Value": experiment_id},
            {"Key": "Name", "Value": "AniFlow-Wan-10min-preflight"}]}
            for kind in ("fleet", "instance", "volume", "network-interface")]}


def _allowed_row(row):
    if not isinstance(row, dict) or row.get("Lifecycle") != "on-demand":
        return False
    launch = row.get("LaunchTemplateAndOverrides")
    override = launch.get("Overrides") if isinstance(launch, dict) else None
    if not isinstance(override, dict) or override.get("InstanceType") not in ALLOWED_TYPES:
        return False
    return row.get("InstanceType", override["InstanceType"]) == override["InstanceType"]


def classify_response(response):
    """Preserve observed IDs even for malformed or partial replies; never authorize a retry."""
    result = {"outcome": "reconcile_required", "instance_ids": [], "error_codes": [],
              "fleet_id": None}
    if not isinstance(response, dict):
        return result
    fleet_id = response.get("FleetId")
    result["fleet_id"] = fleet_id if isinstance(fleet_id, str) else None
    invalid = not isinstance(fleet_id, str) or not FLEET_ID.fullmatch(fleet_id)
    instances, errors = response.get("Instances"), response.get("Errors")
    if not isinstance(instances, list):
        invalid, instances = True, []
    if not isinstance(errors, list):
        invalid, errors = True, []
    for row in instances:
        if not _allowed_row(row):
            invalid = True
        identifiers = row.get("InstanceIds") if isinstance(row, dict) else None
        if not isinstance(identifiers, list) or not identifiers:
            invalid = True
            continue
        for identifier in identifiers:
            if isinstance(identifier, str) and identifier:
                result["instance_ids"].append(identifier)
                if not INSTANCE_ID.fullmatch(identifier):
                    invalid = True
            else:
                invalid = True
    for row in errors:
        if not _allowed_row(row):
            invalid = True
        code = row.get("ErrorCode") if isinstance(row, dict) else None
        if isinstance(code, str) and code:
            result["error_codes"].append(code)
        if not isinstance(code, str) or code not in CAPACITY_ERRORS:
            invalid = True
    count = len(result["instance_ids"])
    if not invalid and count == 1:
        result["outcome"] = "created"
    elif not invalid and count == 0 and errors:
        result["outcome"] = "rejected"
    return result
