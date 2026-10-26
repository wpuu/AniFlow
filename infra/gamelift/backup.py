"""Independent Singapore SSM Automation step; no Lambda dependency."""
import time

import boto3
from botocore.exceptions import ClientError


def handler(events, context):
    client = boto3.client("gameliftstreams", region_name="ap-northeast-1")
    group = events["GroupId"]
    for _ in range(50):
        try:
            current = client.get_stream_group(Identifier=group)
            if current["Status"] != "DELETING":
                client.delete_stream_group(Identifier=group)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                return {"state": "released", "group_id": group}
            if exc.response["Error"]["Code"] not in {"ConflictException", "ThrottlingException"}:
                raise
        time.sleep(10)
    raise RuntimeError("Group deletion was not confirmed; retain guards and investigate")
