"""Fixed-deadline cleanup for an explicitly tagged, disposable experiment."""
import json
import os
import time
from datetime import UTC, datetime

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def api(service):
    return boto3.client(service, region_name="ap-northeast-1", config=Config(
        connect_timeout=5, read_timeout=10, retries={"total_max_attempts": 2, "mode": "standard"}))


def sweep(ws, ds, experiment, stop_due, cleanup_due):
    workspaces = []
    for page in ws.get_paginator("describe_workspaces").paginate():
        for item in page.get("Workspaces", []):
            tags = ws.describe_tags(ResourceId=item["WorkspaceId"])["TagList"]
            if any(t["Key"] == "ExperimentId" and t.get("Value") == experiment for t in tags):
                workspaces.append(item)
    summary = {"matched_workspaces": len(workspaces), "states": [w["State"] for w in workspaces],
               "stop_due": stop_due, "cleanup_due": cleanup_due, "all_resources_absent": False}
    if not stop_due:
        return summary
    for item in workspaces:
        if cleanup_due:
            if item["State"] not in {"TERMINATING", "TERMINATED", "SUSPENDED"}:
                result = ws.terminate_workspaces(TerminateWorkspaceRequests=[{
                    "WorkspaceId": item["WorkspaceId"]}])
            else:
                continue
        elif (item["State"] in {"AVAILABLE", "IMPAIRED", "UNHEALTHY", "ERROR"}
              and item.get("WorkspaceProperties", {}).get("RunningMode") == "AUTO_STOP"):
            result = ws.stop_workspaces(StopWorkspaceRequests=[{"WorkspaceId": item["WorkspaceId"]}])
        else:
            continue
        if result.get("FailedRequests"):
            raise RuntimeError("WorkSpaces returned FailedRequests; cleanup is not confirmed")
    if not cleanup_due or any(w["State"] != "TERMINATED" for w in workspaces):
        return summary

    owned = []
    for page in ds.get_paginator("describe_directories").paginate():
        for directory in page.get("DirectoryDescriptions", []):
            tags = ds.list_tags_for_resource(ResourceId=directory["DirectoryId"])["Tags"]
            if any(t["Key"] == "ExperimentId" and t.get("Value") == experiment for t in tags):
                owned.append(directory)
    registered = {d["DirectoryId"]: d for page in
                  ws.get_paginator("describe_workspace_directories").paginate()
                  for d in page.get("Directories", [])}
    for directory in owned:
        identifier = directory["DirectoryId"]
        if identifier in registered:
            if registered[identifier].get("State") != "DEREGISTERING":
                ws.deregister_workspace_directory(DirectoryId=identifier)
        elif directory.get("Stage") != "Deleting":
            ds.delete_directory(DirectoryId=identifier)
    summary["matched_directories"] = len(owned)
    summary["all_resources_absent"] = not workspaces and not owned
    return summary


def handler(event, context):
    now = datetime.now(UTC)
    stop = datetime.fromisoformat(os.environ["STOP_UTC"])
    cleanup = datetime.fromisoformat(os.environ["CLEANUP_UTC"])
    if cleanup <= stop:
        raise RuntimeError("Cleanup deadline must follow the stop deadline")
    result = sweep(api("workspaces"), api("ds"), os.environ["EXPERIMENT_ID"],
                   now >= stop, now >= cleanup)
    print(json.dumps(result))
    return result


def backup(event, context):
    deadline = datetime.fromisoformat(event["CleanupUtc"])
    if datetime.now(UTC) < deadline:
        raise RuntimeError("Backup refuses to delete before its fixed deadline")
    ws = api("workspaces")
    ds = api("ds")
    until = time.monotonic() + 540
    while time.monotonic() < until:
        try:
            result = sweep(ws, ds, event["ExperimentId"], True, True)
            print(json.dumps(result))
            if result["all_resources_absent"]:
                return result
        except (BotoCoreError, ClientError, RuntimeError) as exc:
            print(json.dumps({"retrying": True, "error_class": type(exc).__name__}))
        time.sleep(15)
    raise RuntimeError("Independent cleanup has not confirmed absence; primary guard remains active")
