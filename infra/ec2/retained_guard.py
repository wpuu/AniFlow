"""Fixed-deadline protection that preserves successfully stopped instances and their disks.

Flush model/video writes and export reports before the deadline. Forced shutdown is the
emergency bound, not a clean application shutdown. No real-GPU validation is implied.
Standalone source embedded in both Lambda and independent Automation.
"""
import json
import os
import re
import time
from datetime import UTC, datetime, timedelta

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

REGION = "us-east-2"
EXPERIMENT = re.compile(r"aniflow-wan-ohio-20261027-[a-z0-9-]+")
API_SECONDS = 8
BACKUP_SECONDS = 120
PHASE = "gpu-retained"


def retained_deadlines(now):
    """Return fresh five/six-minute UTC deadlines, conservatively rounded to whole seconds."""
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        raise ValueError("Retained deadlines require an aware UTC datetime")
    base = now.replace(microsecond=0)
    return {"stop_utc": (base + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cleanup_utc": (base + timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def api():
    client = boto3.client("ec2", region_name=REGION, config=Config(
        connect_timeout=3, read_timeout=5,
        retries={"total_max_attempts": 1, "mode": "standard"}))
    for operation in ("StopInstances", "TerminateInstances"):
        try:
            members = client.meta.service_model.operation_model(operation).input_shape.members
            supported = {"Force", "SkipOsShutdown"}.issubset(members)
        except (AttributeError, BotoCoreError, TypeError):
            supported = False
        if not supported:
            raise RuntimeError("EC2 SDK lacks Force/SkipOsShutdown support for " + operation)
    return client


def timestamp(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def sweep(ec2, experiment, stop_due, cleanup_due, until=None, monotonic=time.monotonic,
          single_page=False):
    if ec2.meta.region_name != REGION or not EXPERIMENT.fullmatch(experiment):
        raise RuntimeError("Unexpected region or experiment; no resource mutation allowed")
    if cleanup_due and not stop_due:
        raise RuntimeError("Cleanup cannot precede the stop deadline")

    def budget():
        if until is not None and until - monotonic() <= API_SECONDS:
            raise RuntimeError("Insufficient time for another bounded EC2 API call")

    instances = []
    request = {"Filters": [{"Name": "tag:ExperimentId", "Values": [experiment]}]}
    while True:
        budget()
        page = ec2.describe_instances(**request)
        for reservation in page.get("Reservations", []):
            for item in reservation.get("Instances", []):
                tags = {tag["Key"]: tag.get("Value") for tag in item.get("Tags", [])}
                if tags.get("ExperimentId") != experiment or tags.get("ExperimentPhase") != PHASE:
                    raise RuntimeError("Instance lacks the exact retained GPU scope tags")
                instances.append(item)
        if not page.get("NextToken"):
            break
        if single_page:
            raise RuntimeError("Partial instance observation leaves final state unconfirmed")
        request["NextToken"] = page["NextToken"]
    states = [item.get("State", {}).get("Name", "unknown") for item in instances]
    if any(state not in {"pending", "running", "stopping", "stopped", "shutting-down", "terminated"}
           for state in states):
        raise RuntimeError("Unknown instance state; no resource mutation allowed")
    summary = {"matched_instances": len(instances), "states": states,
               "stop_due": stop_due, "cleanup_due": cleanup_due,
               "all_compute_stopped": all(state in {"stopped", "terminated"} for state in states),
               "all_compute_released": all(state in {"stopped", "terminated"} for state in states),
               "scope": "Exact-tagged retained GPU compute only; disks and ancillary costs remain unchecked"}
    if not stop_due:
        return summary
    for item in instances:
        state = item.get("State", {}).get("Name", "unknown")
        if cleanup_due:
            if state in {"pending", "running"}:
                budget()
                ec2.terminate_instances(InstanceIds=[item["InstanceId"]],
                                        Force=True, SkipOsShutdown=True)
            elif state == "stopping":
                budget()
                ec2.stop_instances(InstanceIds=[item["InstanceId"]],
                                  Force=True, SkipOsShutdown=True)
        elif state in {"running", "stopping"}:
            budget()
            ec2.stop_instances(InstanceIds=[item["InstanceId"]], Force=True, SkipOsShutdown=True)
    # API acknowledgements cannot prove the final state; a later observation must do so.
    return summary


def handler(event, context):
    now = datetime.now(UTC)
    stop, cleanup = timestamp(os.environ["STOP_UTC"]), timestamp(os.environ["CLEANUP_UTC"])
    if cleanup <= stop:
        raise RuntimeError("Cleanup deadline must follow the stop deadline")
    result = sweep(api(), os.environ["EXPERIMENT_ID"], now >= stop, now >= cleanup)
    print(json.dumps(result))
    return result


def _backup(event, cleanup, now=None, monotonic=time.monotonic, sleep=time.sleep):
    now = now or (lambda: datetime.now(UTC))
    stop, release = timestamp(event["StopUtc"]), timestamp(event["CleanupUtc"])
    if release <= stop:
        raise RuntimeError("Cleanup deadline must follow the stop deadline")
    due = release if cleanup else stop
    if now() < due:
        raise RuntimeError("Backup refuses mutation before its fixed deadline")
    until = monotonic() + BACKUP_SECONDS
    if not cleanup:
        # Leave the following independent cleanup step its original execution deadline.
        until = min(until, monotonic() + max(0, (release - now()).total_seconds()))
    ec2 = api()
    if not cleanup and now() >= release:
        # A delayed stop may only prove existing final state, without postponing cleanup.
        result = sweep(ec2, event["ExperimentId"], False, False, single_page=True)
        print(json.dumps(result))
        if result["all_compute_stopped"]:
            return result
        raise RuntimeError("Late stop final state is unconfirmed; proceed to independent cleanup")
    confirmed = "all_compute_released" if cleanup else "all_compute_stopped"
    while until - monotonic() > API_SECONDS:
        try:
            # Recheck wall time before every sweep, including after retries.
            current = now()
            result = sweep(ec2, event["ExperimentId"], current >= stop,
                           cleanup and current >= release, until, monotonic)
            print(json.dumps(result))
            if result[confirmed]:
                return result
        except (BotoCoreError, ClientError, RuntimeError) as exc:
            print(json.dumps({"retrying": True, "error_class": type(exc).__name__}))
        remaining = until - monotonic() - API_SECONDS
        if remaining > 0:
            sleep(min(5, remaining))
    raise RuntimeError("Tagged compute final state is unconfirmed; ancillary costs are not checked")


def backup_stop(event, context):
    return _backup(event, False)


def backup_cleanup(event, context):
    return _backup(event, True)
