"""Fixed-deadline protection for tagged Ohio EC2 compute, not ancillary billing."""
import json
import os
import re
import time
from datetime import UTC, datetime

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

REGION = "us-east-2"
EXPERIMENT = re.compile(r"aniflow-wan-ohio-20261027-[a-z0-9-]+")


def api():
    return boto3.client("ec2", region_name=REGION, config=Config(
        connect_timeout=5, read_timeout=10,
        retries={"total_max_attempts": 2, "mode": "standard"}))


def timestamp(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def sweep(ec2, experiment, stop_due, cleanup_due):
    if ec2.meta.region_name != REGION or not EXPERIMENT.fullmatch(experiment):
        raise RuntimeError("Unexpected region or experiment; no resource mutation allowed")
    if cleanup_due and not stop_due:
        raise RuntimeError("Cleanup cannot precede the stop deadline")
    instances = []
    for page in ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "tag:ExperimentId", "Values": [experiment]}]
    ):
        for reservation in page.get("Reservations", []):
            for item in reservation.get("Instances", []):
                if any(t["Key"] == "ExperimentId" and t.get("Value") == experiment
                       for t in item.get("Tags", [])):
                    instances.append(item)
    states = [item["State"]["Name"] for item in instances]
    summary = {"matched_instances": len(instances), "states": states,
               "stop_due": stop_due, "cleanup_due": cleanup_due,
               "all_compute_released": all(state == "terminated" for state in states),
               "scope": "Tagged EC2 compute only; volumes, storage and network are not checked"}
    if not stop_due:
        return summary
    for item in instances:
        state = item["State"]["Name"]
        if cleanup_due:
            if state not in {"shutting-down", "terminated"}:
                ec2.terminate_instances(InstanceIds=[item["InstanceId"]])
        elif state == "running":
            ec2.stop_instances(InstanceIds=[item["InstanceId"]])
    # Only the state read above is evidence; mutation acknowledgements are not final states.
    return summary


def handler(event, context):
    now = datetime.now(UTC)
    stop, cleanup = timestamp(os.environ["STOP_UTC"]), timestamp(os.environ["CLEANUP_UTC"])
    if cleanup <= stop:
        raise RuntimeError("Cleanup deadline must follow the stop deadline")
    result = sweep(api(), os.environ["EXPERIMENT_ID"], now >= stop, now >= cleanup)
    print(json.dumps(result))
    return result


def backup(event, context):
    if datetime.now(UTC) < timestamp(event["CleanupUtc"]):
        raise RuntimeError("Backup refuses to terminate before its fixed deadline")
    ec2 = api()
    until = time.monotonic() + 540
    while time.monotonic() < until:
        try:
            result = sweep(ec2, event["ExperimentId"], True, True)
            print(json.dumps(result))
            if result["all_compute_released"]:
                return result
        except (BotoCoreError, ClientError, RuntimeError) as exc:
            print(json.dumps({"retrying": True, "error_class": type(exc).__name__}))
        time.sleep(15)
    raise RuntimeError("Tagged compute release is unconfirmed; ancillary costs are not checked")
