"""Retained-instance double protection; local tests do not imply real-GPU validation."""
from pathlib import Path

from g7_templates import templates as base_templates


def templates():
    primary, backup = base_templates()
    source = Path(__file__).with_name("retained_guard.py").read_text(encoding="utf-8")
    primary["Description"] = "Fixed-deadline Ohio GPU stop protection; preserve stopped instances and disks."
    backup["Description"] = "Independent GPU stop protection; terminate only if compute has not stopped."
    primary["Resources"]["Guard"]["Properties"]["Code"]["ZipFile"] = source
    content = backup["Resources"]["Document"]["Properties"]["Content"]
    content["description"] = "Retain stopped GPUs; export and flush reports before emergency shutdown"
    for step in content["mainSteps"]:
        if step["action"] == "aws:executeScript":
            step["timeoutSeconds"] = 540
            step["inputs"]["Script"] = source
    for template in (primary, backup):
        policy = template["Resources"]["Role"]["Properties"]["Policies"][0]["PolicyDocument"]
        writes = policy["Statement"][1]
        assert set(writes["Action"]) == {"ec2:StopInstances", "ec2:TerminateInstances"}
        writes["Condition"]["StringEquals"]["ec2:ResourceTag/ExperimentPhase"] = "gpu-retained"
    return primary, backup
