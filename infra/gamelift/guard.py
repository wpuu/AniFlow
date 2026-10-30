"""Fixed-deadline, exact-resource GameLift guard. Never allocates capacity."""
import os
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError


def release_application(client):
    application = os.environ.get("APPLICATION_ID")
    if not application:
        return {"state": "released"}
    try:
        current = client.get_application(Identifier=application)
        if current["Status"] != "DELETING":
            client.delete_application(Identifier=application)
        return {"state": "application_deletion_pending"}
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return {"state": "released", "application_id": application}
        raise


def handler(event, context):
    deadline = datetime.fromisoformat(os.environ["DEADLINE_UTC"])
    if datetime.now(UTC) < deadline:
        return {"state": "armed", "deadline_utc": deadline.isoformat()}
    group = os.environ["GROUP_ID"]
    client = boto3.client("gameliftstreams", region_name="ap-northeast-1")
    try:
        current = client.get_stream_group(Identifier=group)
        if current["Status"] != "DELETING":
            client.delete_stream_group(Identifier=group)
        # A successful delete response does not prove capacity release.
        current = client.get_stream_group(Identifier=group)
        return {"state": "deletion_pending", "status": current["Status"]}
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return {**release_application(client), "group_id": group}
        raise
