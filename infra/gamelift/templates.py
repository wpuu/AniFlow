"""Build two small CloudFormation guard stacks, with no positive GPU capacity."""
import json
from pathlib import Path


def templates():
    root = Path(__file__).parent
    parameters = {
        "GroupId": {"Type": "String", "AllowedPattern": "sg-[a-zA-Z0-9]+"},
        "ApplicationId": {"Type": "String", "Default": "", "AllowedPattern": "(|a-[a-zA-Z0-9]+)"},
        "DeadlineUtc": {"Type": "String",
                        "AllowedPattern": "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"},
    }
    policy = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Action": ["gameliftstreams:GetStreamGroup",
                                      "gameliftstreams:DeleteStreamGroup"],
        "Resource": {"Fn::Sub": "arn:${AWS::Partition}:gameliftstreams:ap-northeast-1:${AWS::AccountId}:streamgroup/${GroupId}"},
    }, {"Fn::If": ["HasApplication", {"Effect": "Allow",
        "Action": ["gameliftstreams:GetApplication", "gameliftstreams:DeleteApplication"],
        "Resource": {"Fn::Sub": "arn:${AWS::Partition}:gameliftstreams:ap-northeast-1:${AWS::AccountId}:application/${ApplicationId}"}},
        {"Ref": "AWS::NoValue"}]}]}
    conditions = {"HasApplication": {"Fn::Not": [{"Fn::Equals": [{"Ref": "ApplicationId"}, ""]}]}}

    def role(service):
        return {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}]},
            "Policies": [{"PolicyName": "DeleteExactTokyoGroupOnly", "PolicyDocument": policy}],
        }}

    primary = {"AWSTemplateFormatVersion": "2010-09-09", "Parameters": parameters, "Conditions": conditions,
        "Resources": {"GuardRole": role("lambda.amazonaws.com"),
            "Guard": {"Type": "AWS::Lambda::Function", "Properties": {
                "Runtime": "python3.13", "Handler": "index.handler", "Timeout": 45,
                "Role": {"Fn::GetAtt": ["GuardRole", "Arn"]},
                "Environment": {"Variables": {"GROUP_ID": {"Ref": "GroupId"},
                                              "DEADLINE_UTC": {"Ref": "DeadlineUtc"},
                                              "APPLICATION_ID": {"Ref": "ApplicationId"}}},
                "Code": {"ZipFile": (root / "guard.py").read_text(encoding="utf-8")}}},
            "Tick": {"Type": "AWS::Events::Rule", "Properties": {
                "ScheduleExpression": "rate(1 minute)", "State": "ENABLED",
                "Targets": [{"Id": "FixedDeadline", "Arn": {"Fn::GetAtt": ["Guard", "Arn"]},
                             "RetryPolicy": {"MaximumEventAgeInSeconds": 300,
                                             "MaximumRetryAttempts": 3}}]}},
            "Invoke": {"Type": "AWS::Lambda::Permission", "Properties": {
                "Action": "lambda:InvokeFunction", "FunctionName": {"Ref": "Guard"},
                "Principal": "events.amazonaws.com", "SourceArn": {"Fn::GetAtt": ["Tick", "Arn"]}}}},
        "Outputs": {"Function": {"Value": {"Ref": "Guard"}},
                    "Rule": {"Value": {"Ref": "Tick"}}}}
    backup = {"AWSTemplateFormatVersion": "2010-09-09", "Parameters": parameters, "Conditions": conditions,
        "Resources": {"GuardRole": role("ssm.amazonaws.com"),
            "Document": {"Type": "AWS::SSM::Document", "Properties": {
                "DocumentType": "Automation", "UpdateMethod": "NewVersion",
                "Content": {"schemaVersion": "0.3", "description": "Independent fixed-deadline deletion of one Tokyo GameLift group",
                    "assumeRole": {"Fn::GetAtt": ["GuardRole", "Arn"]},
                    "mainSteps": [{"name": "WaitUntilDeadline", "action": "aws:sleep",
                        "inputs": {"Timestamp": {"Ref": "DeadlineUtc"}}, "nextStep": "DeleteAndVerify"},
                        {"name": "DeleteAndVerify", "action": "aws:executeScript",
                         "timeoutSeconds": 600, "isEnd": True, "inputs": {
                             "Runtime": "python3.11", "Handler": "handler",
                             "InputPayload": {"GroupId": {"Ref": "GroupId"},
                                              "ApplicationId": {"Ref": "ApplicationId"}},
                             "Script": (root / "backup.py").read_text(encoding="utf-8")}}]}}}},
        "Outputs": {"Document": {"Value": {"Ref": "Document"}}}}
    return primary, backup


if __name__ == "__main__":
    for name, body in zip(("primary", "backup"), templates()):
        Path(__file__).with_name(f"{name}-template.json").write_text(
            json.dumps(body, indent=2) + "\n", encoding="utf-8")
