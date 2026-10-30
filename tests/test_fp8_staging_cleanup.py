import hashlib
import importlib.util
import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

ROOT = Path(__file__).parents[1]
EXPERIMENT = "aniflow-wan-ohio-20261027-retained-o"
PREFIX = f"experiments/{EXPERIMENT}/assets/fp8-s/"
NOW = datetime(2026, 10, 29, 18, tzinfo=UTC)
BUCKET = "private-model-bucket"


def module(monkeypatch):
    spec = importlib.util.spec_from_file_location("fp8_staging_cleanup",
        ROOT / "infra/ec2/fp8_staging_cleanup.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    monkeypatch.setattr(result, "utc_now", lambda: NOW)
    return result


def template(runtime, **changes):
    args = {"experiment_id": EXPERIMENT, "bucket": BUCKET,
        "object_keys": [PREFIX + name for name in runtime.FP8_BASENAMES],
        "purge_utc": (NOW + timedelta(hours=2)).isoformat(), **changes}
    return runtime.build_template(**args)


def test_template_is_pure_exact_scope_and_has_no_ec2_permission(monkeypatch):
    runtime = module(monkeypatch)
    monkeypatch.setattr("boto3.client", Mock(side_effect=AssertionError("No AWS during build")))
    result = template(runtime)
    resources = result["Resources"]
    function = resources["Cleanup"]["Properties"]
    assert function["MemorySize"] == 128 and function["Timeout"] == 30
    assert resources["LogGroup"]["Properties"]["RetentionInDays"] == 1
    assert resources["Rule"]["Properties"]["ScheduleExpression"] == "rate(1 minute)"
    assert function["Environment"]["Variables"]["EXPECTED_OWNER"] == {"Ref": "AWS::AccountId"}
    statements = resources["Role"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    actions = {action for row in statements for action in row["Action"]}
    assert actions == {"s3:ListBucketMultipartUploads", "s3:ListBucket", "s3:AbortMultipartUpload", "s3:DeleteObject",
        "s3:GetObject", "logs:CreateLogStream", "logs:PutLogEvents", "events:DisableRule"}
    objects = next(row for row in statements if row["Sid"] == "OnlyTwoTemporaryObjects")
    assert len(objects["Resource"]) == 2
    assert all("*" not in row["Fn::Sub"] and row["Fn::Sub"].startswith("arn:${AWS::Partition}:s3:::")
               for row in objects["Resource"])
    listing = next(row for row in statements if row["Sid"] == "OwnedBucketMultipartMetadata")
    assert "s3:prefix" not in json.dumps(listing)
    exact_listing = next(row for row in statements if row["Sid"] == "OnlyExactObjectMetadata")
    assert exact_listing["Condition"]["StringEquals"]["s3:prefix"] == [PREFIX + name for name in runtime.FP8_BASENAMES]
    rule = next(row for row in statements if row["Sid"] == "OnlyOwnTimer")
    assert rule["Resource"]["Fn::Sub"].endswith("rule/" + EXPERIMENT + "-fp8-s-purge")
    assert "*" not in rule["Resource"]["Fn::Sub"]
    compile(function["Code"]["ZipFile"], "cleanup-handler", "exec")


@pytest.mark.parametrize("changes", [
    {"experiment_id": "unrelated"}, {"bucket": "bad/bucket"},
    {"object_keys": [PREFIX + "unknown", PREFIX + "another"]},
    {"object_keys": ["experiments/unrelated/high", "experiments/unrelated/low"]},
    {"object_keys": [PREFIX + "../high", PREFIX + "low"]},
    {"object_keys": [PREFIX + "same", PREFIX + "same"]},
    {"purge_utc": "2026-10-29T20:00:00"},
    {"purge_utc": "2026-10-30T03:00:00Z"},
    {"purge_utc": "2026-10-29T17:00:00Z"},
])
def test_invalid_scope_or_deadline_is_rejected(monkeypatch, changes):
    with pytest.raises((TypeError, ValueError)):
        template(module(monkeypatch), **changes)


def test_past_deadline_requires_explicit_boolean_proof(monkeypatch):
    runtime = module(monkeypatch)
    result = template(runtime, purge_utc="2026-10-29T17:00:00Z", allow_past_deadline=True)
    assert result["Outputs"]["PurgeUtc"]["Value"] == "2026-10-29T17:00:00Z"
    with pytest.raises(TypeError):
        template(runtime, allow_past_deadline="yes")


def response(code=200, **fields):
    return {"ResponseMetadata": {"HTTPStatusCode": code}, **fields}


def error(code, http_status):
    return ClientError({"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": http_status}}, "Test")


def handler_environment(monkeypatch, *, past=True):
    runtime = module(monkeypatch)
    result = template(runtime, purge_utc=(NOW - timedelta(hours=1) if past else NOW + timedelta(hours=1)).isoformat(),
        allow_past_deadline=past)
    env = result["Resources"]["Cleanup"]["Properties"]["Environment"]["Variables"]
    for key, value in env.items():
        monkeypatch.setenv(key, "123456789012" if isinstance(value, dict) else value)
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    keys = json.loads(env["OBJECT_KEYS_JSON"])
    s3, events = Mock(), Mock()
    s3.list_multipart_uploads.return_value = response(Uploads=[], IsTruncated=False)
    s3.list_objects_v2.return_value = response(Contents=[], KeyCount=0, IsTruncated=False)
    s3.delete_object.return_value = response(204)
    s3.head_object.side_effect = error("404", 404)
    s3.abort_multipart_upload.return_value = response(204)
    events.disable_rule.return_value = response()
    factory = Mock(side_effect=lambda service, **kwargs: {"s3": s3, "events": events}[service])
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=factory))
    namespace = {}
    exec(runtime.HANDLER_SOURCE, namespace)  # noqa: S102 -- Only fake AWS clients are installed.
    namespace["utc_now"] = lambda: NOW
    return namespace["handler"], s3, events, factory, keys


def test_not_due_makes_no_aws_call(monkeypatch):
    handler, _, _, factory, _ = handler_environment(monkeypatch, past=False)
    result = handler({}, None)
    assert result == {"cleanup_due": False, "delete_requests": 0, "rule_disabled": False}
    factory.assert_not_called()


def test_due_empty_scope_confirms_absence_then_disables_own_rule(monkeypatch):
    handler, s3, events, _, keys = handler_environment(monkeypatch)
    result = handler({}, None)
    assert result["objects_absent_verified"] and result["uploads_absent_verified"]
    assert result["delete_requests"] == 2 and result["aborted_uploads"] == 0
    assert [call.kwargs["Key"] for call in s3.delete_object.call_args_list] == keys
    assert all(call.kwargs["Prefix"] == PREFIX for call in s3.list_multipart_uploads.call_args_list)
    assert all(call.kwargs["ExpectedBucketOwner"] == "123456789012" for call in s3.head_object.call_args_list)
    events.disable_rule.assert_called_once_with(Name=EXPERIMENT + "-fp8-s-purge", EventBusName="default")


def test_exact_early_cleanup_can_run_before_deadline(monkeypatch):
    handler, _, _, _, _ = handler_environment(monkeypatch, past=False)
    assert handler({"cleanup_now": True}, None)["early_cleanup"] is True


@pytest.mark.parametrize("payload", [{"force": True}, {"keys": []}, {"cleanup_now": False},
    {"cleanup_now": 1}, {"cleanup_now": True, "keys": []}, None])
def test_unknown_override_payload_cannot_start_cleanup(monkeypatch, payload):
    handler, _, events, factory, _ = handler_environment(monkeypatch)
    with pytest.raises(AssertionError):
        handler(payload, None)
    factory.assert_not_called()
    events.disable_rule.assert_not_called()


def test_abort_only_fixed_uploads_then_verify_no_remaining_uploads(monkeypatch):
    handler, s3, _, _, keys = handler_environment(monkeypatch)
    s3.list_multipart_uploads.side_effect = [response(Uploads=[{"Key": keys[0], "UploadId": "upload-1"}]),
        response(Uploads=[])]
    assert handler({}, None)["aborted_uploads"] == 1
    s3.abort_multipart_upload.assert_called_once_with(Bucket=BUCKET, Key=keys[0], UploadId="upload-1",
        ExpectedBucketOwner="123456789012")


@pytest.mark.parametrize("failure", ["unknown-key", "list-status", "delete-status", "head-forbidden",
    "head-present", "versioned", "abort", "remaining", "pagination"])
def test_unconfirmed_cleanup_never_disables_timer(monkeypatch, failure):
    handler, s3, events, _, keys = handler_environment(monkeypatch)
    if failure == "unknown-key":
        s3.list_multipart_uploads.return_value = response(Uploads=[{"Key": "original-fp16", "UploadId": "other"}])
    elif failure == "list-status":
        s3.list_multipart_uploads.return_value = response(503)
    elif failure == "delete-status":
        s3.delete_object.return_value = response(500)
    elif failure == "head-forbidden":
        s3.head_object.side_effect = error("AccessDenied", 403)
        s3.list_objects_v2.return_value = response(Contents=[{"Key": keys[0]}], KeyCount=1, IsTruncated=False)
    elif failure == "head-present":
        s3.head_object.side_effect = None
        s3.head_object.return_value = response()
    elif failure == "versioned":
        s3.delete_object.return_value = response(204, DeleteMarker=True, VersionId="retained-version")
    elif failure in {"abort", "remaining"}:
        s3.list_multipart_uploads.return_value = response(Uploads=[{"Key": keys[0], "UploadId": "still-active"}])
        if failure == "abort":
            s3.abort_multipart_upload.side_effect = error("AccessDenied", 403)
    elif failure == "pagination":
        s3.list_multipart_uploads.return_value = response(IsTruncated=True)
    with pytest.raises((AssertionError, RuntimeError, ClientError)):
        handler({}, None)
    events.disable_rule.assert_not_called()
    if failure in {"unknown-key", "list-status", "pagination"}:
        s3.delete_object.assert_not_called()
        s3.abort_multipart_upload.assert_not_called()


def test_environment_cannot_redirect_to_other_objects(monkeypatch):
    handler, _, _, factory, _ = handler_environment(monkeypatch)
    monkeypatch.setenv("OBJECT_KEYS_JSON", '["other","original-video"]')
    with pytest.raises(AssertionError):
        handler({}, None)
    factory.assert_not_called()


def test_head_403_requires_independent_exact_empty_listing(monkeypatch):
    handler, s3, _, _, keys = handler_environment(monkeypatch)
    s3.head_object.side_effect = error("AccessDenied", 403)
    result = handler({}, None)
    assert result["object_absence_method"] == "exact-key-list-with-head-check"
    assert [call.kwargs["Prefix"] for call in s3.list_objects_v2.call_args_list] == keys
    assert all(call.kwargs["MaxKeys"] == 2 for call in s3.list_objects_v2.call_args_list)


@pytest.mark.parametrize("failure", ["forbidden", "unexpected-key", "truncated", "unknown-status"])
def test_object_listing_failure_does_not_turn_head_403_into_absence(monkeypatch, failure):
    handler, s3, events, _, keys = handler_environment(monkeypatch)
    s3.head_object.side_effect = error("AccessDenied", 403)
    if failure == "forbidden":
        s3.list_objects_v2.side_effect = error("AccessDenied", 403)
    elif failure == "unexpected-key":
        s3.list_objects_v2.return_value = response(Contents=[{"Key": keys[0] + ".other"}], KeyCount=1)
    elif failure == "truncated":
        s3.list_objects_v2.return_value = response(Contents=[], KeyCount=0, IsTruncated=True)
    else:
        s3.list_objects_v2.return_value = response(503)
    with pytest.raises((AssertionError, ClientError)):
        handler({}, None)
    events.disable_rule.assert_not_called()


def test_optional_download_function_has_separate_exact_write_role(monkeypatch):
    result = template(module(monkeypatch), include_downloader=True)
    resources = result["Resources"]
    download = resources["Download"]["Properties"]
    assert download["MemorySize"] == 512 and download["Timeout"] == 900
    assert download["ReservedConcurrentExecutions"] == 2
    assert download["Role"] == {"Fn::GetAtt": ["DownloadRole", "Arn"]}
    assert download["LoggingConfig"]["LogGroup"] == resources["LogGroup"]["Properties"]["LogGroupName"]
    invoke = resources["DownloadAsync"]["Properties"]
    assert invoke["MaximumRetryAttempts"] == 0 and invoke["MaximumEventAgeInSeconds"] == 60
    statements = resources["DownloadRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    actions = {action for row in statements for action in row["Action"]}
    assert actions == {"s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload", "s3:ListBucket",
        "logs:CreateLogStream", "logs:PutLogEvents"}
    objects = statements[0]["Resource"]
    assert len(objects) == 2 and all("*" not in item["Fn::Sub"] for item in objects)
    exact_listing = next(row for row in statements if row["Sid"] == "OnlyExactObjectMetadata")
    assert exact_listing["Condition"]["StringEquals"]["s3:prefix"] == [PREFIX + name for name in module(monkeypatch).FP8_BASENAMES]
    assert "DeleteObject" not in json.dumps(statements)
    assert "Download" not in template(module(monkeypatch))["Resources"]


def downloader_environment(monkeypatch):
    runtime = module(monkeypatch)
    result = template(runtime, include_downloader=True)
    env = result["Resources"]["Download"]["Properties"]["Environment"]["Variables"]
    for key, value in env.items():
        monkeypatch.setenv(key, "123456789012" if isinstance(value, dict) else value)
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    payloads = [b"verified high", b"verified low"]
    s3 = Mock()
    s3.meta.service_model.operation_model.return_value.input_shape.members = {"IfNoneMatch": {}}
    stored = {"exists": False}
    s3.head_object.side_effect = lambda **kwargs: (response(ContentLength=len(payloads[0]),
        Metadata={"sha256": hashlib.sha256(payloads[0]).hexdigest()}, ServerSideEncryption="AES256")
        if stored["exists"] else (_ for _ in ()).throw(error("404", 404)))
    s3.create_multipart_upload.return_value = response(UploadId="one-fixed-upload")
    s3.list_objects_v2.return_value = response(Contents=[], KeyCount=0, IsTruncated=False)
    s3.upload_part.side_effect = lambda **kwargs: response(ETag="part-" + str(kwargs["PartNumber"]))

    def complete(**kwargs):
        stored["exists"] = True
        return response()

    s3.complete_multipart_upload.side_effect = complete
    s3.abort_multipart_upload.return_value = response(204)
    factory = Mock(return_value=s3)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=factory))
    namespace = {}
    exec(runtime.DOWNLOAD_SOURCE, namespace)  # noqa: S102 -- Public source and S3 clients are fakes.
    assert namespace["MODELS"][0][1] == namespace["MODELS"][1][1] == 14294742832
    assert namespace["MODELS"][0][2] == "6122e79d55e0f235698d11d657f3b196c5273c830da00b2b013c5a048d5e6a42"
    assert namespace["MODELS"][1][2] == "5471a457b6ac404202a5fbe6c11595a3d5641fc766b00f38763f72303fffc21e"
    namespace["MODELS"] = tuple((name, len(data), hashlib.sha256(data).hexdigest())
        for name, data in zip(runtime.FP8_BASENAMES, payloads))
    namespace["READ_BYTES"] = 3
    namespace["utc_now"] = lambda: NOW

    class Source(io.BytesIO):
        status = 200

        def __init__(self, data):
            super().__init__(data)
            self.headers = {"Content-Length": str(len(data))}

        def geturl(self):
            return "https://public-model-cdn.example/model"

    opener = Mock(return_value=Source(payloads[0]))
    namespace["urlopen"] = opener
    context = SimpleNamespace(get_remaining_time_in_millis=Mock(return_value=900000))
    return namespace, s3, factory, opener, context, payloads, stored, Source


def test_downloader_streams_verifies_hash_then_conditionally_completes(monkeypatch):
    namespace, s3, _, opener, context, payloads, _, _ = downloader_environment(monkeypatch)
    result = namespace["handler"]({"index": 0}, context)
    assert result["full_sha256_verified"] and result["bytes"] == len(payloads[0])
    assert b"".join(call.kwargs["Body"] for call in s3.upload_part.call_args_list) == payloads[0]
    created = s3.create_multipart_upload.call_args.kwargs
    assert created["ServerSideEncryption"] == "AES256" and created["Metadata"]["sha256"] == hashlib.sha256(payloads[0]).hexdigest()
    assert s3.complete_multipart_upload.call_args.kwargs["IfNoneMatch"] == "*"
    assert all(call.kwargs["ExpectedBucketOwner"] == "123456789012" for call in s3.upload_part.call_args_list)
    request = opener.call_args.args[0]
    assert request.full_url.startswith("https://www.modelscope.cn/api/v1/models/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/repo?")
    assert "Authorization" not in request.headers
    s3.abort_multipart_upload.assert_not_called()


@pytest.mark.parametrize("payload", [{"index": True}, {"index": 2}, {"index": -1},
    {"index": 0, "url": "https://untrusted.example"}, {"keys": []}, {}, None])
def test_downloader_cannot_accept_urls_or_arbitrary_objects(monkeypatch, payload):
    namespace, _, factory, opener, context, _, _, _ = downloader_environment(monkeypatch)
    with pytest.raises(AssertionError):
        namespace["handler"](payload, context)
    factory.assert_not_called()
    opener.assert_not_called()


def test_existing_verified_model_does_not_download_or_overwrite(monkeypatch):
    namespace, s3, _, opener, context, _, stored, _ = downloader_environment(monkeypatch)
    stored["exists"] = True
    result = namespace["handler"]({"index": 0}, context)
    assert result["already_exists"] and not result["download_performed"]
    s3.create_multipart_upload.assert_not_called()
    opener.assert_not_called()


def test_existing_unknown_model_fails_without_overwriting(monkeypatch):
    namespace, s3, _, opener, context, _, _, _ = downloader_environment(monkeypatch)
    s3.head_object.side_effect = None
    s3.head_object.return_value = response(ContentLength=10, Metadata={"sha256": "wrong"}, ServerSideEncryption="AES256")
    with pytest.raises(AssertionError):
        namespace["handler"]({"index": 0}, context)
    s3.create_multipart_upload.assert_not_called()
    opener.assert_not_called()


@pytest.mark.parametrize("failure", ["hash", "part-status", "deadline", "complete-status"])
def test_failed_stream_aborts_and_never_claims_completed(monkeypatch, failure):
    namespace, s3, _, opener, context, payloads, _, source_type = downloader_environment(monkeypatch)
    if failure == "hash":
        opener.return_value = source_type(b"x" * len(payloads[0]))
    elif failure == "part-status":
        s3.upload_part.side_effect = None
        s3.upload_part.return_value = response(503)
    elif failure == "deadline":
        times = iter([NOW, NOW, NOW + timedelta(hours=3)])
        namespace["utc_now"] = lambda: next(times)
    else:
        s3.complete_multipart_upload.side_effect = None
        s3.complete_multipart_upload.return_value = response(503)
    with pytest.raises(RuntimeError, match="Public FP8 staging failed"):
        namespace["handler"]({"index": 0}, context)
    s3.abort_multipart_upload.assert_called_once()
    if failure != "complete-status":
        s3.complete_multipart_upload.assert_not_called()


def test_download_cannot_begin_near_lambda_timeout(monkeypatch):
    namespace, _, factory, opener, context, _, _, _ = downloader_environment(monkeypatch)
    context.get_remaining_time_in_millis.return_value = 10000
    with pytest.raises(AssertionError):
        namespace["handler"]({"index": 0}, context)
    factory.assert_not_called()
    opener.assert_not_called()


def test_downloader_can_confirm_head_403_only_through_exact_listing(monkeypatch):
    namespace, s3, _, _, context, payloads, stored, _ = downloader_environment(monkeypatch)

    def head(**kwargs):
        if not stored["exists"]:
            raise error("AccessDenied", 403)
        return response(ContentLength=len(payloads[0]),
            Metadata={"sha256": hashlib.sha256(payloads[0]).hexdigest()}, ServerSideEncryption="AES256")

    s3.head_object.side_effect = head
    assert namespace["handler"]({"index": 0}, context)["full_sha256_verified"]
    s3.list_objects_v2.assert_called_once_with(Bucket=BUCKET,
        Prefix=PREFIX + namespace["MODELS"][0][0], MaxKeys=2, ExpectedBucketOwner="123456789012")


def test_downloader_does_not_treat_unknown_listing_as_missing(monkeypatch):
    namespace, s3, _, opener, context, _, _, _ = downloader_environment(monkeypatch)
    s3.head_object.side_effect = error("AccessDenied", 403)
    s3.list_objects_v2.return_value = response(Contents=[{"Key": "unrelated-model"}], KeyCount=1)
    with pytest.raises(AssertionError):
        namespace["handler"]({"index": 0}, context)
    s3.create_multipart_upload.assert_not_called()
    opener.assert_not_called()


def test_unsupported_sdk_fails_before_public_download(monkeypatch):
    namespace, s3, _, opener, context, _, _, _ = downloader_environment(monkeypatch)
    s3.meta.service_model.operation_model.return_value.input_shape.members = {}
    with pytest.raises(AssertionError, match="conditional multipart"):
        namespace["handler"]({"index": 0}, context)
    opener.assert_not_called()
    s3.create_multipart_upload.assert_not_called()
