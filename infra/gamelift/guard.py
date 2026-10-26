"""Fixed-deadline, exact-resource GameLift guard. Never allocates capacity."""
import os
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError


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
            return {"state": "released", "group_id": group}
        raise
