"""Bounded CPU-only transfer of pinned public weights to private Tokyo S3."""
import hashlib
import json
import os
import urllib.request

import boto3
from botocore.exceptions import ClientError


def handler(event, context):
    with open(os.path.join(os.path.dirname(__file__), "models.json"), encoding="utf-8") as source:
        manifest = json.load(source)
    index = event["index"]
    if type(index) is not int or index not in range(4):
        raise ValueError("Invalid pinned asset index")
    asset = manifest["files"][index]
    bucket = os.environ["BUCKET"]
    key = "application/v1/ComfyUI/models/" + asset["path"]
    s3 = boto3.client("s3", region_name="ap-northeast-1")
    try:
        existing = s3.head_object(Bucket=bucket, Key=key)
        if (existing["ContentLength"] == asset["bytes"]
                and existing.get("Metadata", {}).get("sha256") == asset["sha256"]):
            return {"state": "already_verified", "index": index}
        raise ValueError("Existing source differs from the pinned asset")
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
            raise
    upload = s3.create_multipart_upload(Bucket=bucket, Key=key,
        ServerSideEncryption="AES256", Metadata={"sha256": asset["sha256"],
        "revision": manifest["revision"]})["UploadId"]
    completed = False
    try:
        url = ("https://huggingface.co/" + manifest["repository"] + "/resolve/"
               + manifest["revision"] + "/" + asset["path"] + "?download=true")
        request = urllib.request.Request(url, headers={"User-Agent": "AniFlow-pinned-H3-transfer/1"})
        digest, count, parts = hashlib.sha256(), 0, []
        with urllib.request.urlopen(request, timeout=60) as source:
            if int(source.headers.get("Content-Length", asset["bytes"])) != asset["bytes"]:
                raise ValueError("Unexpected source byte count")
            while block := source.read(32 * 1024 * 1024):
                if context.get_remaining_time_in_millis() < 30000:
                    raise TimeoutError("Transfer time budget exhausted")
                count += len(block)
                if count > asset["bytes"]:
                    raise ValueError("Source exceeds pinned byte count")
                digest.update(block)
                number = len(parts) + 1
                response = s3.upload_part(Bucket=bucket, Key=key, UploadId=upload,
                    PartNumber=number, Body=block)
                parts.append({"PartNumber": number, "ETag": response["ETag"]})
        if count != asset["bytes"] or digest.hexdigest() != asset["sha256"]:
            raise ValueError("Full pinned asset SHA256 mismatch")
        s3.complete_multipart_upload(Bucket=bucket, Key=key, UploadId=upload,
                                     MultipartUpload={"Parts": parts})
        completed = True
        result = {"state": "verified", "index": index, **asset}
        s3.put_object(Bucket=bucket, Key=f"manifests/model-{index}.json",
                      Body=json.dumps(result).encode(), ContentType="application/json",
                      ServerSideEncryption="AES256")
        return result
    finally:
        if not completed:
            s3.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload)
