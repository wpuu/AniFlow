"""Independent AWS execution paths; no desktop, directory or capacity creation."""
import json
from pathlib import Path


def templates():
    source = Path(__file__).with_name("gr6_guard.py").read_text(encoding="utf-8")
    parameters = {
        "ExperimentId": {"Type": "String", "AllowedPattern": "aniflow-h3-gr6-[a-z0-9-]+"},
        "StopUtc": {"Type": "String"}, "CleanupUtc": {"Type": "String"}}
    region = {"StringEquals": {"aws:RequestedRegion": "ap-northeast-1"}}
    owned = {"StringEquals": {"aws:RequestedRegion": "ap-northeast-1",
                              "aws:ResourceTag/ExperimentId": {"Ref": "ExperimentId"}}}
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["workspaces:DescribeWorkspaces", "workspaces:DescribeTags",
          "workspaces:DescribeWorkspaceDirectories", "ds:DescribeDirectories", "ds:ListTagsForResource"],
         "Resource": "*", "Condition": region},
        {"Effect": "Allow", "Action": ["workspaces:StopWorkspaces", "workspaces:TerminateWorkspaces"],
         "Resource": {"Fn::Sub": "arn:${AWS::Partition}:workspaces:ap-northeast-1:${AWS::AccountId}:workspace/*"},
         "Condition": owned},
        {"Effect": "Allow", "Action": "workspaces:DeregisterWorkspaceDirectory",
         "Resource": {"Fn::Sub": "arn:${AWS::Partition}:workspaces:ap-northeast-1:${AWS::AccountId}:directory/*"},
         "Condition": owned},
        {"Effect": "Allow", "Action": "ds:DeleteDirectory",
         "Resource": {"Fn::Sub": "arn:${AWS::Partition}:ds:ap-northeast-1:${AWS::AccountId}:directory/*"},
         "Condition": owned}]}

    def role(principal):
        trust = {"Effect": "Allow", "Principal": {"Service": principal}, "Action": "sts:AssumeRole"}
        if principal == "ssm.amazonaws.com":
            trust["Condition"] = {"StringEquals": {"aws:SourceAccount": {"Ref": "AWS::AccountId"}}}
        return {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [trust]},
            "Policies": [{"PolicyName": "CleanOnlyTaggedTokyoExperiment", "PolicyDocument": policy}]}}

    primary = {"AWSTemplateFormatVersion": "2010-09-09", "Parameters": parameters,
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
    for index in range(3):
        steps.append({"name": f"IndependentCleanup{index + 1}", "action": "aws:executeScript",
            "timeoutSeconds": 600, **({"onFailure": "Continue"} if index < 2 else {"isEnd": True}),
            "inputs": {"Runtime": "python3.11", "Handler": "backup", "Script": source,
                "InputPayload": {"ExperimentId": {"Ref": "ExperimentId"},
                                 "CleanupUtc": {"Ref": "CleanupUtc"}}}})
    backup = {"AWSTemplateFormatVersion": "2010-09-09",
        "Parameters": {k: v for k, v in parameters.items() if k != "StopUtc"},
        "Resources": {"Role": role("ssm.amazonaws.com"),
            "Document": {"Type": "AWS::SSM::Document", "Properties": {
                "DocumentType": "Automation", "UpdateMethod": "NewVersion", "Content": {
                    "schemaVersion": "0.3", "description": "Independent fixed-deadline Tokyo experiment cleanup",
                    "assumeRole": {"Fn::GetAtt": ["Role", "Arn"]}, "mainSteps": steps}}}},
        "Outputs": {"Document": {"Value": {"Ref": "Document"}},
                    "Role": {"Value": {"Ref": "Role"}}}}
    return primary, backup


if __name__ == "__main__":
    for name, template in zip(("primary", "backup"), templates()):
        Path(__file__).with_name(f"gr6-{name}-template.json").write_text(
            json.dumps(template, indent=2) + "\n", encoding="utf-8")
