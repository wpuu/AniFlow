import base64
import hashlib
import importlib.util
import io
import json
import shlex
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]
BASE = "/opt/aniflow/wan"


def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "infra/ec2"))
    spec = importlib.util.spec_from_file_location(
        "wan_cached_runtime", ROOT / "infra/ec2/wan_cached_runtime.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def written_files(commands):
    rows = [shlex.split(command) for command in commands if command.startswith("printf %s ")]
    return {row[-1]: base64.b64decode(row[2]).decode() for row in rows}


def execute_generated(source):
    exec(source, {})  # noqa: S102 -- Our generated scripts run with fully mocked I/O.


def test_builders_are_pure_and_restore_only_local_pinned_services(monkeypatch):
    runtime = module(monkeypatch)
    network, process = Mock(side_effect=AssertionError), Mock(side_effect=AssertionError)
    monkeypatch.setattr("socket.socket", network)
    monkeypatch.setattr("subprocess.run", process)
    commands = runtime.build_cached_start_commands()
    files = written_files(commands)
    assert commands.index("systemctl is-active --quiet aniflow-deadline.service") < 4
    unit = files["/etc/systemd/system/aniflow-comfy.service"]
    assert "Requires=aniflow-deadline.service aniflow-wan-cache-verify.service" in unit
    assert "--listen 127.0.0.1 --port 8188 --disable-auto-launch" in unit
    assert "Restart=no" in unit and "systemctl enable --now aniflow-comfy.service" in commands
    all_text = "\n".join(commands) + "\n".join(files.values())
    for forbidden in ("pip install", "apt-get", "curl", "git fetch", "--cpu", "--fp8",
                      "0.0.0.0", "/prompt", "bootstrap.service"):
        assert forbidden not in all_text
    assert runtime.RUNTIME_CAPTURE_TIMEOUT_SECONDS == 120
    assert runtime.build_runtime_capture_commands()[-1].endswith("capture-cached-runtime.py")
    for name in ("verify-retained-cache.py", "capture-cached-runtime.py"):
        compile(files[BASE + "/" + name], name, "exec")
    network.assert_not_called()
    process.assert_not_called()


def environment(runtime, monkeypatch):
    manifest = runtime._manifest()
    stored = {BASE + "/verified-models.json": json.dumps(manifest, indent=2).encode(),
              "/proc/sys/kernel/random/boot_id": b"current-boot"}
    versions = {"torch": "2.11.0+cu130", "torchvision": "0.26.0+cu130",
                "torchaudio": "2.11.0+cu130"}
    stored[BASE + "/base-torch.json"] = json.dumps({
        "torch_file": "/opt/pytorch/lib/torch/__init__.py", "versions": versions}).encode()
    sizes = {BASE + "/ComfyUI/models/" + row["relative_path"]: row["bytes"]
             for row in manifest["models"]}
    links = set()

    class MemoryPath(str):
        def __truediv__(self, other):
            return MemoryPath(self.rstrip("/") + "/" + str(other))

        def resolve(self):
            return self

        def is_relative_to(self, other):
            return self.startswith(str(other).rstrip("/") + "/")

        def is_symlink(self):
            return self in links

        def is_file(self):
            return self in stored or self in sizes

        def stat(self):
            return SimpleNamespace(st_size=sizes[self])

        def read_bytes(self):
            return stored[self]

        def read_text(self):
            return stored[self].decode()

        def write_text(self, value):
            stored[self] = value.encode()

        @property
        def name(self):
            return self.rsplit("/", 1)[-1]

    stop = datetime.now(UTC) + timedelta(minutes=20)
    state = {"stop": stop, "dynamic": True, "cuda": True, "enabled": True}

    def output(args, **kwargs):
        if args[0] == "git":
            return runtime.COMFY_COMMIT
        if list(args[:2]) == ["systemctl", "show"]:
            return "Result=success\nExecMainStatus=0"
        if args[0] == "journalctl" and args[2] == "aniflow-deadline.service":
            return "Started immutable deadline\nWAN_DEADLINE_ARMED:" + state["stop"].isoformat() + "\nDeadline active\n"
        if args[0] == "journalctl" and args[2] == "aniflow-comfy.service":
            return "DynamicVRAM support detected and enabled" if state["dynamic"] else "starting"
        raise AssertionError(args)

    classes = {"LoadImage", "ImageScale", "UNETLoader", "CLIPLoader", "VAELoader",
               "CLIPTextEncode", "ModelSamplingSD3", "WanImageToVideo", "KSamplerAdvanced",
               "VAEDecode", "CreateVideo", "SaveVideo"}
    schema = {name: {} for name in classes}
    for node, key, names in (
        ("UNETLoader", "unet_name", [row[0].rsplit("/", 1)[-1] for row in runtime.MODELS[:2]]),
        ("CLIPLoader", "clip_name", [runtime.MODELS[2][0].rsplit("/", 1)[-1]]),
        ("VAELoader", "vae_name", [runtime.MODELS[3][0].rsplit("/", 1)[-1]]),
    ):
        schema[node] = {"input": {"required": {key: [names]}}}

    class Opener:
        def open(self, url, timeout):
            assert timeout == 15 and url.startswith("http://127.0.0.1:8188/")
            data = schema if url.endswith("/object_info") else {"devices": [{"type": "cuda"}]}
            return io.BytesIO(json.dumps(data).encode())

    comfy = ModuleType("comfy")
    comfy.__path__ = []
    management = ModuleType("comfy.model_management")
    for name in ("get_torch_device", "text_encoder_device", "vae_device"):
        setattr(management, name, lambda: "cuda:0" if state["cuda"] else "cpu")
    torch = SimpleNamespace(__file__="/opt/pytorch/lib/torch/__init__.py",
                            cuda=SimpleNamespace(is_available=lambda: state["cuda"],
                                                 device_count=lambda: 1))
    monkeypatch.setattr("pathlib.Path", MemoryPath)
    monkeypatch.setattr("subprocess.check_output", output)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0 if state["enabled"] else 1))
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    monkeypatch.setattr("importlib.metadata.version", versions.__getitem__)
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.model_management", management)
    monkeypatch.setitem(sys.modules, "torch", torch)
    return stored, sizes, links, state


def test_current_boot_cache_and_runtime_evidence_are_real_checks_not_bootstrap_claim(monkeypatch, capsys):
    runtime = module(monkeypatch)
    commands = written_files(runtime.build_cached_start_commands())
    with monkeypatch.context() as patch:
        stored, _, _, _ = environment(runtime, patch)
        execute_generated(commands[BASE + "/verify-retained-cache.py"])
        cache = json.loads(stored[BASE + "/cached-restore-verification.json"])
        assert cache["manifest_sha256"] == hashlib.sha256(stored[BASE + "/verified-models.json"]).hexdigest()
        before = list(sys.path)
        try:
            execute_generated(commands[BASE + "/capture-cached-runtime.py"])
        finally:
            sys.path[:] = before
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["cache_restore_verified"] and result["cache_verification"]["boot_id"] == "current-boot"
    assert result["full_hash_recomputed_this_boot"] is False
    assert result["model_inference_verified"] is False and result["real_video_generated"] is False
    assert result["deadline_service_active"] and result["comfy_service_active"]
    assert result["object_info_required_nodes_present"] and result["model_choices_verified"]
    assert "bootstrap" not in result


@pytest.mark.parametrize("failure", ["manifest", "size", "symlink", "expired"])
def test_cache_rejects_tampered_audit_model_or_expired_deadline(monkeypatch, failure):
    runtime = module(monkeypatch)
    source = written_files(runtime.build_cached_start_commands())[BASE + "/verify-retained-cache.py"]
    with monkeypatch.context() as patch:
        stored, sizes, links, state = environment(runtime, patch)
        if failure == "manifest":
            stored[BASE + "/verified-models.json"] += b"\n"
        elif failure == "size":
            sizes[next(iter(sizes))] -= 1
        elif failure == "symlink":
            links.add(next(iter(sizes)))
        else:
            state["stop"] = datetime.now(UTC) - timedelta(seconds=1)
        with pytest.raises(AssertionError):
            execute_generated(source)
        assert BASE + "/cached-restore-verification.json" not in stored


@pytest.mark.parametrize("failure", ["prior_boot", "dynamic", "cuda", "enabled"])
def test_runtime_rejects_old_boot_missing_dynamic_cuda_or_service(monkeypatch, failure):
    runtime = module(monkeypatch)
    scripts = written_files(runtime.build_cached_start_commands())
    with monkeypatch.context() as patch:
        stored, _, _, state = environment(runtime, patch)
        execute_generated(scripts[BASE + "/verify-retained-cache.py"])
        if failure == "prior_boot":
            stored["/proc/sys/kernel/random/boot_id"] = b"another-boot"
        else:
            state[failure] = False
        before = list(sys.path)
        try:
            with pytest.raises(AssertionError):
                execute_generated(scripts[BASE + "/capture-cached-runtime.py"])
        finally:
            sys.path[:] = before
