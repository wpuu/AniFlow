"""Draft-only ephemeral GPU preflight protection; no deployment or real-GPU revalidation."""
from pathlib import Path

from g7_templates import templates as base_templates


def templates():
    primary, backup = base_templates()
    source = Path(__file__).with_name("preflight_guard.py").read_text(encoding="utf-8")
    primary["Description"] = "Draft ephemeral GPU preflight force-stop protection; no models or video."
    backup["Description"] = "Draft independent ephemeral GPU preflight force-stop and termination."
    primary["Resources"]["Guard"]["Properties"]["Code"]["ZipFile"] = source
    content = backup["Resources"]["Document"]["Properties"]["Content"]
    content["description"] = "Ephemeral GPU preflight only; reports saved before forceful shutdown"
    for step in content["mainSteps"]:
        if step["action"] == "aws:executeScript":
            step["inputs"]["Script"] = source
    for template in (primary, backup):
        policy = template["Resources"]["Role"]["Properties"]["Policies"][0]["PolicyDocument"]
        writes = policy["Statement"][1]
        assert set(writes["Action"]) == {"ec2:StopInstances", "ec2:TerminateInstances"}
        writes["Condition"]["StringEquals"]["ec2:ResourceTag/ExperimentPhase"] = "gpu-preflight"
    return primary, backup
