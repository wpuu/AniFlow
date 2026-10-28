"""Short independent G7 protection built without changing the shared WAN templates."""
from pathlib import Path

from wan_templates import templates as wan_templates


def templates():
    primary, backup = wan_templates()
    source = Path(__file__).with_name("g7_guard.py").read_text(encoding="utf-8")
    primary["Description"] = (
        "Short fixed-deadline Ohio G7 compute protection; ancillary costs need separate cleanup.")
    guard = primary["Resources"]["Guard"]["Properties"]
    guard["Code"]["ZipFile"] = source
    guard["Timeout"] = 25
    primary["Resources"]["Tick"]["Properties"]["Targets"][0]["RetryPolicy"] = {
        "MaximumEventAgeInSeconds": 60, "MaximumRetryAttempts": 0}
    primary["Resources"]["Invocation"] = {"Type": "AWS::Lambda::EventInvokeConfig",
        "Properties": {"FunctionName": {"Ref": "Guard"}, "Qualifier": "$LATEST",
                       "MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 60}}
    backup["Description"] = "Independent fixed-deadline Ohio G7 stop and termination protection."
    backup["Parameters"]["StopUtc"] = primary["Parameters"]["StopUtc"].copy()
    content = backup["Resources"]["Document"]["Properties"]["Content"]
    content["description"] = "Independent tagged Ohio G7 stop followed by termination"
    payload = {"ExperimentId": {"Ref": "ExperimentId"},
               "StopUtc": {"Ref": "StopUtc"}, "CleanupUtc": {"Ref": "CleanupUtc"}}
    stop = {"name": "IndependentStop", "action": "aws:executeScript",
        "timeoutSeconds": 150, "maxAttempts": 1, "onFailure": "Continue",
        "inputs": {"Runtime": "python3.11", "Handler": "backup_stop", "Script": source,
                   "InputPayload": payload.copy()}}
    cleanup = {"name": "IndependentCleanup", "action": "aws:executeScript",
        "timeoutSeconds": 150, "maxAttempts": 1, "isEnd": True,
        "inputs": {"Runtime": "python3.11", "Handler": "backup_cleanup", "Script": source,
                   "InputPayload": payload.copy()}}
    content["mainSteps"] = [
        {"name": "WaitUntilStop", "action": "aws:sleep",
         "inputs": {"Timestamp": {"Ref": "StopUtc"}}}, stop,
        {"name": "WaitUntilCleanup", "action": "aws:sleep",
         "inputs": {"Timestamp": {"Ref": "CleanupUtc"}}}, cleanup]
    return primary, backup
