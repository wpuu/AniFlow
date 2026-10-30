"""Build an exact-two-object temporary FP8 cleanup guard; never execute AWS calls."""
import json
import re
from datetime import UTC, datetime, timedelta

CREDIT_EXPIRY_UTC = datetime(2026, 10, 30, 3, 29, 56, tzinfo=UTC)
FP8_BASENAMES = (
    "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
    "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
)


def utc_now():
    return datetime.now(UTC)


def build_template(experiment_id, bucket, object_keys, purge_utc, *, allow_past_deadline=False,
                   include_downloader=False):
    """Return an Ohio deployment template; past deadlines require explicit proof mode."""
    if (not isinstance(experiment_id, str)
            or not re.fullmatch(r"aniflow-wan-ohio-20261027-[a-z0-9-]+", experiment_id)
            or len(experiment_id + "-fp8-s-download") > 64):
        raise ValueError("Invalid owner experiment identifier")
    if not isinstance(bucket, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Invalid private bucket")
    prefix = f"experiments/{experiment_id}/assets/fp8-s/"
    expected = [prefix + name for name in FP8_BASENAMES]
    if not isinstance(object_keys, (list, tuple)) or list(object_keys) != expected:
        raise ValueError("Only the two exact owner FP8 staging keys are allowed")
    if not isinstance(allow_past_deadline, bool):
        raise TypeError("Past-deadline proof permission must be a boolean")
    if not isinstance(include_downloader, bool):
        raise TypeError("The optional downloader must be explicitly enabled")
    if not isinstance(purge_utc, str):
        raise TypeError("The cleanup deadline must be an ISO timestamp")
    deadline = datetime.fromisoformat(purge_utc)
    if deadline.tzinfo is None or deadline.utcoffset() != timedelta(0):
        raise ValueError("The cleanup deadline must have an explicit UTC offset")
    deadline = deadline.replace(microsecond=0)
    if deadline > CREDIT_EXPIRY_UTC - timedelta(minutes=30):
        raise ValueError("Cleanup must precede credit expiry by at least 30 minutes")
    if deadline <= utc_now() and not allow_past_deadline:
        raise ValueError("A past cleanup deadline is permitted only for explicit empty-key proof")
    rule = experiment_id + "-fp8-s-purge"
    function = experiment_id + "-fp8-s-cleanup"
    group = "/aws/lambda/" + function
    tags = [{"Key": "ExperimentId", "Value": experiment_id},
            {"Key": "Purpose", "Value": "temporary-fp8-models"}]
    statements = [
        # ListBucketMultipartUploads has no s3:prefix condition key in AWS's action table.
        # The list grant is metadata-only for this bucket; code constrains Prefix and exact keys.
        {"Sid": "OwnedBucketMultipartMetadata", "Effect": "Allow",
         "Action": ["s3:ListBucketMultipartUploads"], "Resource": "arn:aws:s3:::" + bucket,
         "Condition": {"StringEquals": {"s3:ResourceAccount": {"Ref": "AWS::AccountId"}}}},
        {"Sid": "OnlyTwoTemporaryObjects", "Effect": "Allow",
         "Action": ["s3:AbortMultipartUpload", "s3:DeleteObject", "s3:GetObject"],
         "Resource": ["arn:aws:s3:::" + bucket + "/" + key for key in expected],
         "Condition": {"StringEquals": {"s3:ResourceAccount": {"Ref": "AWS::AccountId"}}}},
        {"Sid": "OnlyExactObjectMetadata", "Effect": "Allow", "Action": ["s3:ListBucket"],
         "Resource": "arn:aws:s3:::" + bucket,
         "Condition": {"StringEquals": {"s3:prefix": expected,
             "s3:ResourceAccount": {"Ref": "AWS::AccountId"}}}},
        {"Sid": "OnlyOwnLogs", "Effect": "Allow",
         "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": {"Fn::Sub": "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:" + group + ":*"}},
        {"Sid": "OnlyOwnTimer", "Effect": "Allow", "Action": ["events:DisableRule"],
         "Resource": {"Fn::Sub": "arn:${AWS::Partition}:events:${AWS::Region}:${AWS::AccountId}:rule/" + rule}},
    ]
    # Use Fn::Sub for the partition instead of hard-coding an account or commercial ARN.
    for statement in statements[:3]:
        resource = statement["Resource"]
        statement["Resource"] = ({"Fn::Sub": resource.replace("arn:aws:", "arn:${AWS::Partition}:")}
                                 if isinstance(resource, str) else
                                 [{"Fn::Sub": value.replace("arn:aws:", "arn:${AWS::Partition}:")}
                                  for value in resource])
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Independent fixed-deadline cleanup of only two temporary FP8 staging objects.",
        "Metadata": {"Purpose": "temporary-fp8-models", "ExactObjectCount": 2,
                     "MultipartListPermissionBoundary": "one bucket, code-enforced prefix and exact keys"},
        "Resources": {
            "LogGroup": {"Type": "AWS::Logs::LogGroup", "Properties": {
                "LogGroupName": group, "RetentionInDays": 1, "Tags": tags}},
            "Role": {"Type": "AWS::IAM::Role", "Properties": {
                "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{
                    "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"}]}, "Tags": tags,
                "Policies": [{"PolicyName": "exact-fp8-temporary-cleanup",
                    "PolicyDocument": {"Version": "2012-10-17", "Statement": statements}}]}},
            "Cleanup": {"Type": "AWS::Lambda::Function", "DependsOn": ["LogGroup"], "Properties": {
                "FunctionName": function, "Runtime": "python3.12", "Handler": "index.handler",
                "MemorySize": 128, "Timeout": 30, "Role": {"Fn::GetAtt": ["Role", "Arn"]},
                "Tags": tags, "Code": {"ZipFile": HANDLER_SOURCE},
                "Environment": {"Variables": {"EXPERIMENT_ID": experiment_id, "BUCKET": bucket,
                    "OBJECT_KEYS_JSON": json.dumps(expected), "PREFIX": prefix,
                    "PURGE_UTC": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"), "RULE_NAME": rule,
                    "EXPECTED_OWNER": {"Ref": "AWS::AccountId"}}}}},
            "Permission": {"Type": "AWS::Lambda::Permission", "Properties": {
                "Action": "lambda:InvokeFunction", "FunctionName": {"Ref": "Cleanup"},
                "Principal": "events.amazonaws.com", "SourceAccount": {"Ref": "AWS::AccountId"},
                "SourceArn": {"Fn::GetAtt": ["Rule", "Arn"]}}},
            "Rule": {"Type": "AWS::Events::Rule", "Properties": {"Name": rule,
                "Description": "Purge exact temporary FP8 keys at a fixed deadline; no EC2 permissions.",
                "State": "ENABLED", "ScheduleExpression": "rate(1 minute)",
                "Targets": [{"Id": "ExactTemporaryModelCleanup", "Arn": {"Fn::GetAtt": ["Cleanup", "Arn"]}}]}},
        },
        "Outputs": {"Function": {"Value": {"Ref": "Cleanup"}}, "Role": {"Value": {"Ref": "Role"}},
            "Rule": {"Value": {"Ref": "Rule"}}, "LogGroup": {"Value": {"Ref": "LogGroup"}},
            "Prefix": {"Value": prefix}, "PurgeUtc": {"Value": deadline.strftime("%Y-%m-%dT%H:%M:%SZ")}},
    }
    if include_downloader:
        _add_downloader(template, experiment_id, bucket, expected, tags, group)
    return template


def _add_downloader(template, experiment, bucket, keys, tags, group):
    variables = dict(template["Resources"]["Cleanup"]["Properties"]["Environment"]["Variables"])
    function = experiment + "-fp8-s-download"
    resources = template["Resources"]
    resources["DownloadRole"] = {"Type": "AWS::IAM::Role", "Properties": {
        "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
        "Tags": tags, "Policies": [{"PolicyName": "exact-two-public-model-downloads",
            "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Sid": "OnlyTwoModelObjects", "Effect": "Allow",
                 "Action": ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"],
                 "Resource": [{"Fn::Sub": "arn:${AWS::Partition}:s3:::" + bucket + "/" + key} for key in keys],
                 "Condition": {"StringEquals": {"s3:ResourceAccount": {"Ref": "AWS::AccountId"}}}},
                {"Sid": "OnlyExactObjectMetadata", "Effect": "Allow", "Action": ["s3:ListBucket"],
                 "Resource": {"Fn::Sub": "arn:${AWS::Partition}:s3:::" + bucket},
                 "Condition": {"StringEquals": {"s3:prefix": keys,
                     "s3:ResourceAccount": {"Ref": "AWS::AccountId"}}}},
                {"Sid": "OnlySharedGuardLogs", "Effect": "Allow",
                 "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                 "Resource": {"Fn::Sub": "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:" + group + ":*"}},
            ]}}]}}
    resources["Download"] = {"Type": "AWS::Lambda::Function", "DependsOn": ["LogGroup"], "Properties": {
        "FunctionName": function, "Runtime": "python3.12", "Handler": "index.handler",
        "MemorySize": 512, "Timeout": 900, "ReservedConcurrentExecutions": 2,
        "Role": {"Fn::GetAtt": ["DownloadRole", "Arn"]}, "Tags": tags,
        "LoggingConfig": {"LogGroup": group}, "Code": {"ZipFile": DOWNLOAD_SOURCE},
        "Environment": {"Variables": variables}}}
    resources["DownloadAsync"] = {"Type": "AWS::Lambda::EventInvokeConfig", "Properties": {
        "FunctionName": {"Ref": "Download"}, "Qualifier": "$LATEST",
        "MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 60}}
    template["Outputs"]["DownloadFunction"] = {"Value": {"Ref": "Download"}}
    template["Outputs"]["DownloadRole"] = {"Value": {"Ref": "DownloadRole"}}


HANDLER_SOURCE = '''import json,os,re
from datetime import datetime,timedelta,timezone
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BASENAMES=('wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors','wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors')

def utc_now():
    return datetime.now(timezone.utc)

def status(response,expected):
    assert response.get('ResponseMetadata',{}).get('HTTPStatusCode')==expected,'Unconfirmed AWS response status'

def handler(event,context):
    assert os.environ['AWS_REGION']=='us-east-2','Wrong cleanup region'
    experiment=os.environ['EXPERIMENT_ID']
    assert re.fullmatch(r'aniflow-wan-ohio-20261027-[a-z0-9-]+',experiment)
    bucket=os.environ['BUCKET']
    assert re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',bucket)
    owner=os.environ['EXPECTED_OWNER']
    assert re.fullmatch(r'[0-9]{12}',owner)
    prefix='experiments/'+experiment+'/assets/fp8-s/'
    keys=[prefix+name for name in BASENAMES]
    assert json.loads(os.environ['OBJECT_KEYS_JSON'])==keys and os.environ['PREFIX']==prefix
    rule=experiment+'-fp8-s-purge'
    assert os.environ['RULE_NAME']==rule and len(rule)<=64
    deadline=datetime.fromisoformat(os.environ['PURGE_UTC'])
    assert deadline.tzinfo is not None and deadline.utcoffset()==timedelta(0)
    assert deadline<=datetime(2026,10,30,3,29,56,tzinfo=timezone.utc)-timedelta(minutes=30)
    immediate=isinstance(event,dict) and set(event)=={'cleanup_now'} and event['cleanup_now'] is True
    if not immediate:
        assert isinstance(event,dict) and set(event).issubset({'version','id','detail-type','source','account','time','region','resources','detail'}),'Unsupported cleanup payload'
        if event:
            assert event.get('source')=='aws.events' and event.get('region')=='us-east-2'
        if utc_now()<deadline:
            return {'cleanup_due':False,'delete_requests':0,'rule_disabled':False}
    config=Config(connect_timeout=3,read_timeout=5,retries={'total_max_attempts':1})
    s3=boto3.client('s3',region_name='us-east-2',config=config)
    events=boto3.client('events',region_name='us-east-2',config=config)

    def uploads():
        result=[]
        markers={}
        seen=set()
        for _ in range(10):
            page=s3.list_multipart_uploads(Bucket=bucket,Prefix=prefix,ExpectedBucketOwner=owner,MaxUploads=1000,**markers)
            status(page,200)
            for item in page.get('Uploads',[]):
                assert item.get('Key') in keys and isinstance(item.get('UploadId'),str) and item['UploadId'],'Unexpected multipart identity'
                result.append((item['Key'],item['UploadId']))
            if not page.get('IsTruncated',False):
                return result
            pair=(page.get('NextKeyMarker'),page.get('NextUploadIdMarker'))
            assert all(isinstance(value,str) and value for value in pair) and pair not in seen,'Invalid multipart pagination'
            seen.add(pair)
            markers={'KeyMarker':pair[0],'UploadIdMarker':pair[1]}
        raise RuntimeError('Multipart scan exceeds bounded cleanup window')

    active=uploads()
    for key,identifier in active:
        try:
            reply=s3.abort_multipart_upload(Bucket=bucket,Key=key,UploadId=identifier,ExpectedBucketOwner=owner)
            status(reply,204)
        except ClientError as error:
            assert error.response.get('Error',{}).get('Code')=='NoSuchUpload' and error.response.get('ResponseMetadata',{}).get('HTTPStatusCode')==404
    for key in keys:
        reply=s3.delete_object(Bucket=bucket,Key=key,ExpectedBucketOwner=owner)
        status(reply,204)
        assert 'DeleteMarker' not in reply and 'VersionId' not in reply,'Versioned bucket cannot prove full temporary deletion'
    for key in keys:
        try:
            s3.head_object(Bucket=bucket,Key=key,ExpectedBucketOwner=owner)
        except ClientError as error:
            code=error.response.get('Error',{}).get('Code')
            http=error.response.get('ResponseMetadata',{}).get('HTTPStatusCode')
            assert (http==404 and code in {'404','NoSuchKey','NotFound'}) or (http==403 and code in {'403','AccessDenied','Forbidden'}),'Object state is unconfirmed'
        else:
            raise RuntimeError('Temporary object still present after cleanup')
        page=s3.list_objects_v2(Bucket=bucket,Prefix=key,MaxKeys=2,ExpectedBucketOwner=owner)
        status(page,200)
        rows=page.get('Contents',[])
        assert isinstance(rows,list) and not page.get('IsTruncated',False) and len(rows)<=1
        assert all(row.get('Key')==key for row in rows),'Unexpected key in restricted object listing'
        assert page.get('KeyCount',len(rows))==len(rows) and rows==[],'Exact object absence is unconfirmed'
    assert uploads()==[],'Temporary multipart uploads remain'
    reply=events.disable_rule(Name=rule,EventBusName='default')
    status(reply,200)
    return {'cleanup_due':True,'early_cleanup':immediate,'exact_key_count':2,
        'delete_requests':2,'aborted_uploads':len(active),'objects_absent_verified':True,
        'uploads_absent_verified':True,'object_absence_method':'exact-key-list-with-head-check',
        'rule_disable_acknowledged':True}
'''


DOWNLOAD_SOURCE = '''import hashlib,json,os,re
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

MODELS=(
 ('wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors',14294742832,'6122e79d55e0f235698d11d657f3b196c5273c830da00b2b013c5a048d5e6a42'),
 ('wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors',14294742832,'5471a457b6ac404202a5fbe6c11595a3d5641fc766b00f38763f72303fffc21e'))
READ_BYTES=64*1024**2

def utc_now():
    return datetime.now(timezone.utc)

def status(response,expected):
    assert response.get('ResponseMetadata',{}).get('HTTPStatusCode')==expected,'Unconfirmed AWS response status'

def handler(event,context):
    assert isinstance(event,dict) and set(event)=={'index'} and type(event['index']) is int and event['index'] in (0,1),'Only a fixed model index is accepted'
    assert os.environ['AWS_REGION']=='us-east-2'
    experiment=os.environ['EXPERIMENT_ID']
    assert re.fullmatch(r'aniflow-wan-ohio-20261027-[a-z0-9-]+',experiment)
    prefix='experiments/'+experiment+'/assets/fp8-s/'
    keys=[prefix+model[0] for model in MODELS]
    assert os.environ['PREFIX']==prefix and json.loads(os.environ['OBJECT_KEYS_JSON'])==keys
    bucket=os.environ['BUCKET']
    owner=os.environ['EXPECTED_OWNER']
    assert re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',bucket) and re.fullmatch(r'[0-9]{12}',owner)
    deadline=datetime.fromisoformat(os.environ['PURGE_UTC'])
    assert deadline.tzinfo is not None and deadline.utcoffset()==timedelta(0)
    assert deadline<=datetime(2026,10,30,3,29,56,tzinfo=timezone.utc)-timedelta(minutes=30)

    def remaining():
        assert utc_now()<deadline,'Temporary staging deadline reached'
        assert context.get_remaining_time_in_millis()>20000,'Insufficient execution time to finish safely'

    remaining()
    name,expected_bytes,expected_sha=MODELS[event['index']]
    key=keys[event['index']]
    client=boto3.client('s3',region_name='us-east-2',config=Config(connect_timeout=3,read_timeout=10,retries={'total_max_attempts':1}))
    assert 'IfNoneMatch' in client.meta.service_model.operation_model('CompleteMultipartUpload').input_shape.members,'Runtime SDK lacks conditional multipart completion'

    def verify_existing(head):
        status(head,200)
        assert head.get('ContentLength')==expected_bytes and head.get('Metadata',{}).get('sha256')==expected_sha and head.get('ServerSideEncryption')=='AES256','Existing staging object is not the verified model'

    try:
        head=client.head_object(Bucket=bucket,Key=key,ExpectedBucketOwner=owner)
    except ClientError as error:
        code=error.response.get('Error',{}).get('Code')
        http=error.response.get('ResponseMetadata',{}).get('HTTPStatusCode')
        assert (http==404 and code in {'404','NoSuchKey','NotFound'}) or (http==403 and code in {'403','AccessDenied','Forbidden'}),'Staging object state is unknown'
        page=client.list_objects_v2(Bucket=bucket,Prefix=key,MaxKeys=2,ExpectedBucketOwner=owner)
        status(page,200)
        rows=page.get('Contents',[])
        assert isinstance(rows,list) and not page.get('IsTruncated',False) and len(rows)<=1
        assert all(row.get('Key')==key for row in rows),'Unexpected key in restricted object listing'
        assert page.get('KeyCount',len(rows))==len(rows) and rows==[],'Staging object absence is unconfirmed'
    else:
        verify_existing(head)
        return {'index':event['index'],'already_exists':True,'expected_identity_verified':True,'download_performed':False}
    query=urlencode({'Revision':'master','FilePath':'split_files/diffusion_models/'+name})
    url='https://www.modelscope.cn/api/v1/models/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/repo?'+query
    request=Request(url,headers={'Accept-Encoding':'identity','User-Agent':'AniFlow-public-model-staging/1'})
    upload_id=None
    try:
        with urlopen(request,timeout=15) as source:
            assert source.status==200 and urlsplit(source.geturl()).scheme=='https','Unexpected public source response'
            assert source.headers.get('Content-Encoding','identity')=='identity'
            assert int(source.headers.get('Content-Length','-1'))==expected_bytes,'Public source length mismatch'
            remaining()
            created=client.create_multipart_upload(Bucket=bucket,Key=key,ServerSideEncryption='AES256',
                Metadata={'sha256':expected_sha,'source':'modelscope-mirror-matches-pinned-comfy-org'},ExpectedBucketOwner=owner)
            status(created,200)
            upload_id=created['UploadId']
            assert isinstance(upload_id,str) and upload_id
            parts=[]
            digest=hashlib.sha256()
            count=0
            while True:
                remaining()
                block=source.read(READ_BYTES)
                if not block:
                    break
                count+=len(block)
                assert count<=expected_bytes,'Public source exceeds exact model size'
                digest.update(block)
                remaining()
                number=len(parts)+1
                reply=client.upload_part(Bucket=bucket,Key=key,UploadId=upload_id,PartNumber=number,
                    Body=block,ContentLength=len(block),ExpectedBucketOwner=owner)
                status(reply,200)
                assert isinstance(reply.get('ETag'),str) and reply['ETag']
                parts.append({'PartNumber':number,'ETag':reply['ETag']})
            assert count==expected_bytes and digest.hexdigest()==expected_sha,'Complete public model SHA256 mismatch'
            remaining()
            reply=client.complete_multipart_upload(Bucket=bucket,Key=key,UploadId=upload_id,
                MultipartUpload={'Parts':parts},IfNoneMatch='*',ExpectedBucketOwner=owner)
            status(reply,200)
            verify_existing(client.head_object(Bucket=bucket,Key=key,ExpectedBucketOwner=owner))
        return {'index':event['index'],'already_exists':False,'full_sha256_verified':True,
            'bytes':count,'parts':len(parts),'download_performed':True}
    except Exception as error:
        if upload_id is not None:
            try:
                client.abort_multipart_upload(Bucket=bucket,Key=key,UploadId=upload_id,ExpectedBucketOwner=owner)
            except Exception:
                pass
        raise RuntimeError('Public FP8 staging failed: '+type(error).__name__) from None
'''
