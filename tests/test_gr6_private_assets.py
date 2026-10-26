import fnmatch
import json
from pathlib import Path

import pytest

TEMPLATE = json.loads((Path(__file__).parents[1]
    / "infra/workspaces/gr6-private-assets-template.json").read_text())
RESOURCES = TEMPLATE["Resources"]
BUCKET = RESOURCES["AssetsBucket"]["Properties"]
ROLE = RESOURCES["HybridNodeRole"]["Properties"]
STATEMENTS = ROLE["Policies"][0]["PolicyDocument"]["Statement"]


def test_storage_is_private_encrypted_and_has_no_versioning_or_acl():
    assert set(BUCKET["PublicAccessBlockConfiguration"]) == {
        "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"}
    assert all(BUCKET["PublicAccessBlockConfiguration"].values())
    assert BUCKET["OwnershipControls"]["Rules"] == [{"ObjectOwnership": "BucketOwnerEnforced"}]
    encryption = BUCKET["BucketEncryption"]["ServerSideEncryptionConfiguration"]
    assert encryption == [{"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
    assert "VersioningConfiguration" not in BUCKET and "AccessControl" not in BUCKET


def test_plain_http_is_denied_for_both_bucket_and_all_objects():
    policy = RESOURCES["AssetsBucketPolicy"]["Properties"]["PolicyDocument"]["Statement"]
    assert len(policy) == 1
    deny = policy[0]
    assert (deny["Effect"], deny["Principal"], deny["Action"]) == ("Deny", "*", "s3:*")
    assert deny["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}
    assert deny["Resource"] == [
        {"Fn::GetAtt": ["AssetsBucket", "Arn"]}, {"Fn::Sub": "${AssetsBucket.Arn}/*"}]


def test_lifecycle_covers_all_objects_and_partial_uploads_without_retention():
    rules = BUCKET["LifecycleConfiguration"]["Rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["Status"] == "Enabled" and rule["Prefix"] == ""
    assert rule["ExpirationInDays"] == 1
    assert rule["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"] == 1
    assert "TagFilters" not in rule
    assert RESOURCES["AssetsBucket"]["DeletionPolicy"] == "Delete"
    notes = " ".join(TEMPLATE["Metadata"]["OperatingNotes"])
    assert "not an exact" in notes and "Explicitly empty and delete" in notes


def test_only_core_ssm_and_scoped_s3_permissions_are_added():
    assert ROLE["ManagedPolicyArns"] == [{"Fn::Sub":
        "arn:${AWS::Partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"}]
    assert len(ROLE["Policies"]) == 1 and len(STATEMENTS) == 2
    assert all(s["Effect"] == "Allow" for s in STATEMENTS)
    listing, objects = STATEMENTS
    assert listing["Action"] == "s3:ListBucket"
    assert listing["Resource"] == {"Fn::GetAtt": ["AssetsBucket", "Arn"]}
    assert set(objects["Action"]) == {"s3:GetObject", "s3:PutObject"}
    assert objects["Resource"] == [
        {"Fn::Sub": "${AssetsBucket.Arn}/outputs/*"},
        {"Fn::Sub": "${AssetsBucket.Arn}/reports/*"}]


@pytest.mark.parametrize("prefix,allowed", [
    ("outputs/", True), ("reports/job.json", True), ("", False),
    ("models/", False), ("outputs-other/", False)])
def test_listing_is_limited_to_output_and_report_prefixes(prefix, allowed):
    patterns = STATEMENTS[0]["Condition"]["StringLike"]["s3:prefix"]
    assert any(fnmatch.fnmatchcase(prefix, pattern) for pattern in patterns) == allowed


@pytest.mark.parametrize("resource,allowed", [
    ("arn:aws:s3:::owned/outputs/video.mp4", True),
    ("arn:aws:s3:::owned/reports/gpu.json", True),
    ("arn:aws:s3:::owned/models/weights.bin", False),
    ("arn:aws:s3:::other/outputs/video.mp4", False),
    ("arn:aws:s3:::owned/video.mp4", False)])
def test_object_permissions_cannot_reach_other_buckets_or_prefixes(resource, allowed):
    patterns = [r["Fn::Sub"].replace("${AssetsBucket.Arn}", "arn:aws:s3:::owned")
                for r in STATEMENTS[1]["Resource"]]
    assert any(fnmatch.fnmatchcase(resource, pattern) for pattern in patterns) == allowed


def test_hybrid_trust_is_same_account_tokyo_and_only_names_are_output():
    trust = ROLE["AssumeRolePolicyDocument"]["Statement"]
    assert len(trust) == 1 and trust[0]["Principal"] == {"Service": "ssm.amazonaws.com"}
    assert trust[0]["Action"] == "sts:AssumeRole"
    conditions = trust[0]["Condition"]
    assert conditions["StringEquals"]["aws:SourceAccount"] == {"Ref": "AWS::AccountId"}
    assert conditions["ArnLike"]["aws:SourceArn"] == {"Fn::Sub":
        "arn:${AWS::Partition}:ssm:ap-northeast-1:${AWS::AccountId}:*"}
    assert {v["Value"]["Ref"] for v in TEMPLATE["Outputs"].values()} == {
        "AssetsBucket", "HybridNodeRole"}
    assert sorted(r["Type"] for r in RESOURCES.values()) == [
        "AWS::IAM::Role", "AWS::S3::Bucket", "AWS::S3::BucketPolicy"]
    for resource in (BUCKET, ROLE):
        assert {"Key": "ExperimentId", "Value": {"Ref": "ExperimentId"}} in resource["Tags"]
