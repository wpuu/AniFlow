import base64
import hashlib
import importlib.util
import io
import json
import shlex
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]


def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "infra/ec2"))
    spec = importlib.util.spec_from_file_location(
        "wan_fp8_runtime", ROOT / "infra/ec2/wan_fp8_runtime.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def source_from_commands(commands):
    command = next(row for row in commands if " -c " in row)
    bootstrap = shlex.split(command)[-1]
    encoded = bootstrap.split("base64.b64decode(", 1)[1].split(")", 1)[0]
    import ast
    return base64.b64decode(ast.literal_eval(encoded)).decode()


def test_builders_are_pure_and_do_not_approve_or_format_disk(monkeypatch):
    runtime = module(monkeypatch)
    process = Mock(side_effect=AssertionError("No process during build"))
    network = Mock(side_effect=AssertionError("No network during build"))
    monkeypatch.setattr("subprocess.run", process)
    monkeypatch.setattr("socket.socket", network)
    probe = source_from_commands(runtime.build_disk_probe_commands())
    assert "'read_only':True" in probe and "'disk_approved':False" in probe
    assert "lsblk" in probe and "findmnt" in probe and "f_bavail*space.f_frsize" in probe
    commands = runtime.build_fp8_copy_commands(bucket="private-model-bucket",
        object_keys=["fp8/high", "fp8/low"], expected_owner="123456789012")
    source = source_from_commands(commands)
    compile(source, "fp8-copy", "exec")
    compile(probe, "fp8-probe", "exec")
    assert runtime.REQUIRED_NEW_BYTES == 28589485664
    assert runtime.REQUIRED_NEW_BYTES + runtime.RESERVE_BYTES == 37179420256
    for forbidden in ("pip install", "start-instances", "/prompt",
                      "unlink(", "rmtree", "systemctl restart", "systemctl start"):
        assert forbidden not in source + probe
    assert "verified-models-fp8-scaled.json" in source
    assert "workflow-bundle-fp8-scaled.json" in source
    assert "cfg.get('allow_instance_store') is True" in source
    process.assert_not_called()
    network.assert_not_called()


@pytest.mark.parametrize("change", [
    {"bucket": "bad/bucket"}, {"expected_owner": "123"},
    {"object_keys": ["same", "same"]}, {"object_keys": ["../bad", "low"]},
    {"object_keys": ["high\n", "low"]}, {"object_keys": [{} , "low"]},
])
def test_source_inputs_are_exact_and_fail_closed(monkeypatch, change):
    runtime = module(monkeypatch)
    args = {"bucket": "private-model-bucket", "object_keys": ["high", "low"],
            "expected_owner": "123456789012", **change}
    with pytest.raises(ValueError):
        runtime.build_fp8_copy_commands(**args)


def test_instance_store_permission_cannot_be_a_truthy_string(monkeypatch):
    runtime = module(monkeypatch)
    with pytest.raises(TypeError):
        runtime.build_fp8_copy_commands(bucket="private-model-bucket",
            object_keys=["high", "low"], expected_owner="123456789012",
            allow_instance_store="yes")


def environment(runtime, monkeypatch, tmp_path, *, free=None, minutes=20):
    root = tmp_path / "wan"
    models = root / "ComfyUI/models"
    models.mkdir(parents=True)
    boot = tmp_path / "boot-id"
    boot.write_text("same-boot")
    old_rows = []
    for index, name in enumerate(("diffusion_models/old-high", "diffusion_models/old-low",
                                  "text_encoders/old-t5", "vae/old-vae")):
        path = models / name
        path.parent.mkdir(exist_ok=True)
        data = bytes([index + 1])
        path.write_bytes(data)
        old_rows.append({"relative_path": name, "bytes": 1,
                        "sha256": hashlib.sha256(data).hexdigest(), "verified": True})
    original = json.dumps({"models": old_rows}, indent=2).encode()
    (root / "verified-models.json").write_bytes(original)
    payloads = [b"high", b"low"]
    new_rows = [{"relative_path": "diffusion_models/new-" + label,
                 "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "verified": True}
                for label, data in zip(("high", "low"), payloads)]
    manifest = {"comfyui_commit": "pinned-commit", "models": new_rows + old_rows[2:]}
    cfg = {"bucket": "private-model-bucket", "owner": "123456789012",
           "object_keys": ["high", "low"], "reserve_bytes": runtime.RESERVE_BYTES,
           "original_sha256": hashlib.sha256(original).hexdigest(),
           "manifest": manifest, "manifest_filename": runtime.MANIFEST_FILENAME,
           "bundle": {"profile": "fp8-scaled"}}
    client = Mock()
    client.head_object.side_effect = [
        {"ContentLength": len(data), "ServerSideEncryption": "AES256"} for data in payloads]
    client.get_object.side_effect = [
        {"ContentLength": len(data), "Body": io.BytesIO(data)} for data in payloads]
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=Mock(return_value=client)))
    monkeypatch.setitem(sys.modules, "botocore.config", SimpleNamespace(Config=lambda **kwargs: kwargs))
    monkeypatch.setattr("os.statvfs", lambda path: SimpleNamespace(
        f_bavail=runtime.RESERVE_BYTES + 7 if free is None else free, f_frsize=1), raising=False)
    stop = datetime.now(UTC) + timedelta(minutes=minutes)
    monkeypatch.setattr("subprocess.run", Mock())
    monkeypatch.setattr("subprocess.check_output", lambda args, **kwargs:
        "pinned-commit" if args[0] == "git" else "WAN_DEADLINE_ARMED:" + stop.isoformat() + "\n")
    source = runtime._COPY.replace("@@CONFIG@@", repr(json.dumps(cfg)))
    source = source.replace("Path('/opt/aniflow/wan')", "Path(" + repr(str(root)) + ")")
    source = source.replace("Path('/proc/sys/kernel/random/boot_id')", "Path(" + repr(str(boot)) + ")")
    return root, models, original, client, source, cfg


def test_actual_generated_copy_hashes_new_files_and_preserves_old_audit(monkeypatch, tmp_path, capsys):
    runtime = module(monkeypatch)
    root, models, original, client, source, cfg = environment(runtime, monkeypatch, tmp_path)
    exec(source, {})  # noqa: S102 -- Execute the generated script only against isolated fake services.
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["new_experts_full_hash_verified"] is True
    assert receipt["comfy_started"] is False and receipt["real_video_generated"] is False
    assert (root / "verified-models.json").read_bytes() == original
    assert (models / "diffusion_models/old-high").read_bytes() == b"\x01"
    assert (models / "diffusion_models/new-high").read_bytes() == b"high"
    assert json.loads((root / runtime.MANIFEST_FILENAME).read_text()) == cfg["manifest"]
    assert json.loads((root / "physical-layout-fp8-scaled.json").read_text())["expert_files_sha256_verified"] is True
    assert client.get_object.call_count == 2
    assert all(call.kwargs["ExpectedBucketOwner"] == "123456789012"
               for call in client.get_object.call_args_list)


@pytest.mark.parametrize("failure", ["space", "expired", "old-manifest", "hash", "sse"])
def test_actual_generated_copy_rejects_unsafe_state_before_success(monkeypatch, tmp_path, failure):
    runtime = module(monkeypatch)
    root, models, _original, client, source, _cfg = environment(runtime, monkeypatch, tmp_path,
        free=runtime.RESERVE_BYTES + 6 if failure == "space" else None,
        minutes=-1 if failure == "expired" else 20)
    if failure == "old-manifest":
        (root / "verified-models.json").write_bytes(b"altered")
    if failure == "hash":
        client.get_object.side_effect = [{"ContentLength": 4, "Body": io.BytesIO(b"evil")}]
    if failure == "sse":
        client.head_object.side_effect = [{"ContentLength": 4, "ServerSideEncryption": "aws:kms"}]
    with pytest.raises(AssertionError):
        exec(source, {})  # noqa: S102 -- Isolated fake filesystem and S3 only.
    assert not (root / runtime.MANIFEST_FILENAME).exists()
    assert not (models / "diffusion_models/new-high").exists()
    if failure in ("space", "expired", "old-manifest"):
        client.get_object.assert_not_called()


def test_final_free_space_must_retain_reserve_before_success(monkeypatch, tmp_path):
    runtime = module(monkeypatch)
    root, _, original, _, source, _ = environment(runtime, monkeypatch, tmp_path)
    calls = {"count": 0}

    def space(path):
        calls["count"] += 1
        return SimpleNamespace(f_bavail=runtime.RESERVE_BYTES + 7 if calls["count"] == 1
                               else runtime.RESERVE_BYTES - 1, f_frsize=1)

    monkeypatch.setattr("os.statvfs", space, raising=False)
    with pytest.raises(AssertionError, match="safety reserve"):
        exec(source, {})  # noqa: S102 -- Isolated fake filesystem and S3 only.
    assert (root / "verified-models.json").read_bytes() == original
    assert not (root / runtime.MANIFEST_FILENAME).exists()


@pytest.mark.parametrize("failure", ["model", "partition", "mounted", "filesystem",
    "size", "parent", "readonly", "blkid", "wipefs", "holder", "identity", "shadow", None])
def test_nvme_fallback_rejects_unproven_disk_without_formatting(monkeypatch, tmp_path, failure):
    import os
    import stat
    runtime = module(monkeypatch)
    root, models, _, client, source, _ = environment(runtime, monkeypatch, tmp_path,
        free=runtime.RESERVE_BYTES + 6)
    if failure == "shadow":
        (models / "diffusion_models/new-high").write_bytes(b"unknown")
    source = source.replace('"reserve_bytes": 8589934592',
                            '"reserve_bytes": 8589934592, "allow_instance_store": true')
    mount = tmp_path / "nvme-mount"
    source = source.replace("Path('/mnt/aniflow-fp8')", "Path(" + repr(str(mount)) + ")")
    sysfs = tmp_path / "sysfs"
    source = source.replace("Path('/sys/class/block')", "Path(" + repr(str(sysfs)) + ")")
    for directory in ("holders", "slaves"):
        (sysfs / "nvme1n1" / directory).mkdir(parents=True)
    if failure == "holder":
        (sysfs / "nvme1n1/holders/dm-0").touch()
    disk = {"name": "nvme1n1", "path": "/dev/nvme1n1", "type": "disk",
            "size": 250000000000, "fstype": None, "mountpoints": [None],
            "model": "Amazon EC2 NVMe Instance Storage", "serial": "AWS-local",
            "pkname": None, "ro": False, "maj:min": "259:1"}
    changes = {"model": {"model": "Amazon Elastic Block Store"},
               "partition": {"children": [{"name": "nvme1n1p1"}]},
               "mounted": {"mountpoints": ["/"]}, "filesystem": {"fstype": "ext4"},
               "size": {"size": 180000000000}, "parent": {"pkname": "nvme0n1"},
               "readonly": {"ro": True}}
    disk.update(changes.get(failure, {}))
    real_stat, real_is_mount = os.stat, Path.is_mount
    mounted = {"value": False}

    def fake_stat(path, *args, **kwargs):
        if str(path) == "/dev/nvme1n1":
            return SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=98765)
        result = real_stat(path, *args, **kwargs)
        if str(path) == str(mount) and mounted["value"]:
            return SimpleNamespace(st_mode=result.st_mode, st_dev=98765, st_ino=result.st_ino)
        return result

    def run_command(args, **kwargs):
        if args[0] in {"mkfs.ext4", "mount"}:
            assert kwargs["capture_output"] is True and kwargs["text"] is True
        if args[0] == "mount":
            mounted["value"] = True
        return SimpleNamespace(returncode=2 if failure != "blkid" else 0, stdout="", stderr="")

    monkeypatch.setattr(os, "stat", fake_stat)
    monkeypatch.setattr(Path, "is_mount", lambda path:
        mounted["value"] if str(path) == str(mount) else real_is_mount(path))
    monkeypatch.setattr(os, "statvfs", lambda path: SimpleNamespace(
        f_bavail=runtime.RESERVE_BYTES + (10 if str(path).startswith(str(mount)) else 6),
        f_frsize=1), raising=False)
    run = Mock(side_effect=run_command)
    monkeypatch.setattr("subprocess.run", run)
    stop = datetime.now(UTC) + timedelta(minutes=20)

    observations = []

    def output(args, **kwargs):
        observations.append(args[0])
        if args[0] == "git":
            return "pinned-commit"
        if args[0] == "journalctl":
            return "WAN_DEADLINE_ARMED:" + stop.isoformat() + "\n"
        if args[0] == "lsblk":
            if failure == "identity" and observations.count("lsblk") == 2:
                disk["serial"] = "changed-device"
            return json.dumps({"blockdevices": [disk]})
        if args[0] == "wipefs":
            return json.dumps({"signatures": [{}] if failure == "wipefs" else []})
        raise AssertionError(args)

    monkeypatch.setattr("subprocess.check_output", output)
    if failure is None:
        exec(source, {})  # noqa: S102 -- Never format a real disk during this test.
        operations = [call.args[0][0] for call in run.call_args_list]
        assert operations.count("mkfs.ext4") == operations.count("mount") == 1
        assert observations.count("lsblk") == observations.count("wipefs") == 2
        layout = json.loads((root / "physical-layout-fp8-scaled.json").read_text())
        assert layout["placement"]["blank_signature_probes"] is True
        assert layout["expert_models_root"] == str(mount / "models")
        assert (mount / "models/diffusion_models/new-high").read_bytes() == b"high"
        intent = json.loads((root / "fp8-instance-store-format-intent-same-boot.json").read_text())
        assert intent["blank_signature_probes"] and intent["disk_identity_rechecked_before_format"]
        assert intent["device"]["model"] == "Amazon EC2 NVMe Instance Storage"
    else:
        with pytest.raises(AssertionError):
            exec(source, {})  # noqa: S102 -- Only fake block devices are exposed.
        assert "lsblk" in observations or failure == "shadow"
        assert not any(call.args[0][0] in ("mkfs.ext4", "mount") for call in run.call_args_list)
        assert not (root / "fp8-instance-store-format-intent-same-boot.json").exists()
        assert not (root / runtime.MANIFEST_FILENAME).exists()
        client.get_object.assert_not_called()
