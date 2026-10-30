"""Separate Ohio Lambda and Singapore Automation guards; no GPU or network creation."""
from pathlib import Path


def templates():
    source = Path(__file__).with_name("wan_guard.py").read_text(encoding="utf-8")
    parameters = {
        "ExperimentId": {"Type": "String", "AllowedPattern": "aniflow-wan-ohio-20261027-[a-z0-9-]+"},
        "StopUtc": {"Type": "String", "AllowedPattern": r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"},
        "CleanupUtc": {"Type": "String", "AllowedPattern": r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"}}
    owned = {"StringEquals": {"aws:RequestedRegion": "us-east-2",
                              "ec2:ResourceTag/ExperimentId": {"Ref": "ExperimentId"}}}
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "ec2:DescribeInstances", "Resource": "*",
         "Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-2"}}},
        {"Effect": "Allow", "Action": ["ec2:StopInstances", "ec2:TerminateInstances"],
         "Resource": {"Fn::Sub": "arn:${AWS::Partition}:ec2:us-east-2:${AWS::AccountId}:instance/*"},
         "Condition": owned}]}

    def role(principal):
        trust = {"Effect": "Allow", "Principal": {"Service": principal}, "Action": "sts:AssumeRole"}
        if principal == "ssm.amazonaws.com":
            trust["Condition"] = {"StringEquals": {"aws:SourceAccount": {"Ref": "AWS::AccountId"}}}
        return {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [trust]},
            "Policies": [{"PolicyName": "ProtectOnlyTaggedOhioCompute", "PolicyDocument": policy}]}}

    def region_rule(region):
        return {"GuardRegion": {"Assertions": [{
            "Assert": {"Fn::Equals": [{"Ref": "AWS::Region"}, region]},
            "AssertDescription": "This guard must be deployed in " + region}]}}

    primary = {"AWSTemplateFormatVersion": "2010-09-09", "Parameters": parameters,
        "Description": "Fixed-deadline Ohio EC2 compute protection; ancillary costs need separate cleanup.",
        "Rules": region_rule("us-east-2"),
        "Resources": {"Role": role("lambda.amazonaws.com"),
            "Logs": {"Type": "AWS::Logs::LogGroup", "Properties": {"RetentionInDays": 1}},
            "Guard": {"Type": "AWS::Lambda::Function", "Properties": {
                "Runtime": "python3.13", "Handler": "index.handler", "Timeout": 60, "MemorySize": 128,
                "Role": {"Fn::GetAtt": ["Role", "Arn"]},
                "Environment": {"Variables": {"EXPERIMENT_ID": {"Ref": "ExperimentId"},
                    "STOP_UTC": {"Ref": "StopUtc"}, "CLEANUP_UTC": {"Ref": "CleanupUtc"}}},
                "Code": {"ZipFile": source}, "LoggingConfig": {"LogGroup": {"Ref": "Logs"}}}},
            "Tick": {"Type": "AWS::Events::Rule", "Properties": {
                "ScheduleExpression": "rate(1 minute)", "State": "ENABLED",
                "Targets": [{"Id": "Guard", "Arn": {"Fn::GetAtt": ["Guard", "Arn"]},
                    "RetryPolicy": {"MaximumEventAgeInSeconds": 60, "MaximumRetryAttempts": 2}}]}},
            "Invoke": {"Type": "AWS::Lambda::Permission", "Properties": {
                "Action": "lambda:InvokeFunction", "FunctionName": {"Ref": "Guard"},
                "Principal": "events.amazonaws.com", "SourceArn": {"Fn::GetAtt": ["Tick", "Arn"]}}}},
        "Outputs": {"Function": {"Value": {"Ref": "Guard"}}, "Rule": {"Value": {"Ref": "Tick"}},
                    "Role": {"Value": {"Ref": "Role"}}, "LogGroup": {"Value": {"Ref": "Logs"}}}}
    primary["Resources"]["Role"]["Properties"]["Policies"].append({
        "PolicyName": "WriteOwnGuardLogs", "PolicyDocument": {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": {"Fn::GetAtt": ["Logs", "Arn"]}}]}})
    steps = [{"name": "WaitUntilCleanup", "action": "aws:sleep",
              "inputs": {"Timestamp": {"Ref": "CleanupUtc"}}}]
    steps.append({"name": "IndependentCleanup", "action": "aws:executeScript",
        "timeoutSeconds": 600, "maxAttempts": 3, "isEnd": True,
        "inputs": {"Runtime": "python3.11", "Handler": "backup", "Script": source,
            "InputPayload": {"ExperimentId": {"Ref": "ExperimentId"},
                             "CleanupUtc": {"Ref": "CleanupUtc"}}}})
    backup = {"AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Independent fixed-deadline Ohio EC2 termination; no primary Lambda dependency.",
        "Rules": region_rule("ap-southeast-1"),
        "Parameters": {k: v for k, v in parameters.items() if k != "StopUtc"},
        "Resources": {"Role": role("ssm.amazonaws.com"),
            "Document": {"Type": "AWS::SSM::Document", "Properties": {
                "DocumentType": "Automation", "UpdateMethod": "NewVersion", "Content": {
                    "schemaVersion": "0.3", "description": "Independent tagged Ohio EC2 termination",
                    "assumeRole": {"Fn::GetAtt": ["Role", "Arn"]}, "mainSteps": steps}}}},
        "Outputs": {"Document": {"Value": {"Ref": "Document"}},
                    "Role": {"Value": {"Ref": "Role"}}}}
    return primary, backup
