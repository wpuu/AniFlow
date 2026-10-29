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


def environment(runtime, monkeypatch, profile="fp16", models_root=None):
    manifest = runtime._manifest(profile)
    stored = {BASE + "/verified-models.json": json.dumps(manifest, indent=2).encode(),
              "/proc/sys/kernel/random/boot_id": b"current-boot"}
    if profile == "fp8-scaled":
        from wan_fp8 import build_bundle
        stored[BASE + "/verified-models.json"] = json.dumps(runtime._manifest(), indent=2).encode()
        stored[BASE + "/verified-models-fp8-scaled.json"] = json.dumps(manifest, indent=2).encode()
        stored[BASE + "/workflow-bundle-fp8-scaled.json"] = json.dumps(build_bundle()).encode()
        stored["/proc/1694/environ"] = b"ANIFLOW_WAN_PROFILE=fp8-scaled\0"
        stored["/proc/1694/cmdline"] = b"\0".join((b"python", b"main.py", b"--listen",
                                                     b"127.0.0.1", b"--port", b"8188"))
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
    if profile == "fp8-scaled":
        selected = models_root or runtime.DEFAULT_MODELS_ROOT
        stored[BASE + "/physical-layout-fp8-scaled.json"] = json.dumps({
            "profile": profile, "expert_models_root": selected, "boot_id": "current-boot",
            "deadline_utc": stop.isoformat(), "expert_files_sha256_verified": True}).encode()
        monkeypatch.setenv("ANIFLOW_EXPECTED_EXPERT_ROOT", selected)
        if selected == runtime.FP8_NVME_MODELS_ROOT:
            for row in manifest["models"][:2]:
                sizes[selected + "/" + row["relative_path"]] = sizes.pop(BASE + "/ComfyUI/models/" + row["relative_path"])
            stored["/proc/1694/cmdline"] += b"\0--extra-model-paths-config\0/opt/aniflow/wan/extra-model-paths-fp8-scaled.yaml"
            stored[BASE + "/extra-model-paths-fp8-scaled.yaml"] = b"aniflow_fp8:\n  base_path: /mnt/aniflow-fp8/models\n  diffusion_models: diffusion_models\n"
    state = {"stop": stop, "dynamic": True, "cuda": True, "enabled": True}

    def output(args, **kwargs):
        if args[0] == "git":
            return runtime.COMFY_COMMIT
        if "MainPID" in args:
            return "1694"
        if "InvocationID" in args:
            return "a" * 32
        if list(args[:2]) == ["systemctl", "show"]:
            return "Result=success\nExecMainStatus=0"
        if args[0] == "journalctl" and args[2] == "aniflow-deadline.service":
            return "Started immutable deadline\nWAN_DEADLINE_ARMED:" + state["stop"].isoformat() + "\nDeadline active\n"
        if args[0] == "journalctl" and args[2] == "aniflow-comfy.service":
            return "DynamicVRAM support detected and enabled" if state["dynamic"] else "starting"
        if args[0] == "journalctl" and args[1].startswith("_SYSTEMD_INVOCATION_ID="):
            assert args[1] == "_SYSTEMD_INVOCATION_ID=" + "a" * 32
            return "DynamicVRAM support detected and enabled" if state["dynamic"] else "starting"
        raise AssertionError(args)

    classes = {"LoadImage", "ImageScale", "UNETLoader", "CLIPLoader", "VAELoader",
               "CLIPTextEncode", "ModelSamplingSD3", "WanImageToVideo", "KSamplerAdvanced",
               "VAEDecode", "CreateVideo", "SaveVideo"}
    schema = {name: {} for name in classes}
    for node, key, names in (
        ("UNETLoader", "unet_name", [row["relative_path"].rsplit("/", 1)[-1] for row in manifest["models"][:2]]),
        ("CLIPLoader", "clip_name", [manifest["models"][2]["relative_path"].rsplit("/", 1)[-1]]),
        ("VAELoader", "vae_name", [manifest["models"][3]["relative_path"].rsplit("/", 1)[-1]]),
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


def test_fp8_builders_force_restart_and_keep_fp16_audit_and_scripts(monkeypatch):
    runtime = module(monkeypatch)
    network, process = Mock(side_effect=AssertionError), Mock(side_effect=AssertionError)
    monkeypatch.setattr("socket.socket", network)
    monkeypatch.setattr("subprocess.run", process)
    commands = runtime.build_cached_start_commands(profile="fp8-scaled")
    files = written_files(commands)
    assert BASE + "/verify-retained-cache.py" not in files
    assert BASE + "/verified-models.json" not in files
    assert BASE + "/verified-models-fp8-scaled.json" not in files
    assert "/etc/systemd/system/aniflow-wan-cache-verify.service" not in files
    assert commands.index("systemctl stop aniflow-comfy.service") < commands.index("systemctl daemon-reload")
    assert commands.index("systemctl restart aniflow-wan-cache-verify-fp8-scaled.service") < commands.index("systemctl restart aniflow-comfy.service")
    assert "systemctl enable --now aniflow-comfy.service" not in commands
    unit = files["/etc/systemd/system/aniflow-comfy.service"]
    assert "Environment=ANIFLOW_WAN_PROFILE=fp8-scaled" in unit
    assert "Requires=aniflow-deadline.service aniflow-wan-cache-verify-fp8-scaled.service" in unit
    assert "--listen 127.0.0.1 --port 8188 --disable-auto-launch" in unit
    assert runtime.build_runtime_capture_commands(profile="fp8-scaled")[-1].endswith("capture-cached-runtime-fp8-scaled.py")
    for name in ("verify-retained-cache-fp8-scaled.py", "capture-cached-runtime-fp8-scaled.py"):
        compile(files[BASE + "/" + name], name, "exec")
        assert "pip install" not in files[BASE + "/" + name]
        assert "/prompt" not in files[BASE + "/" + name]
    assert hashlib.sha256(json.dumps(runtime._manifest(), indent=2).encode()).hexdigest() == "2179ba579f12ce1cf4fc30f2e1ae4d589811203914660777f998b8181ec93974"
    network.assert_not_called()
    process.assert_not_called()


def test_fp8_fresh_process_manifest_and_configuration_are_observed_not_inference(monkeypatch, capsys):
    runtime = module(monkeypatch)
    scripts = written_files(runtime.build_cached_start_commands(profile="fp8-scaled"))
    with monkeypatch.context() as patch:
        stored, _, _, _ = environment(runtime, patch, profile="fp8-scaled")
        original = stored[BASE + "/verified-models.json"]
        execute_generated(scripts[BASE + "/verify-retained-cache-fp8-scaled.py"])
        before = list(sys.path)
        try:
            execute_generated(scripts[BASE + "/capture-cached-runtime-fp8-scaled.py"])
        finally:
            sys.path[:] = before
        assert stored[BASE + "/verified-models.json"] == original
        assert BASE + "/cached-restore-verification.json" not in stored
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["profile"] == "fp8-scaled" and result["process_profile_verified"] is True
    assert result["manifest_filename"] == "verified-models-fp8-scaled.json"
    assert result["cache_verification"]["profile"] == result["verified_models"]["profile"]
    assert result["configured_expert_choices"] == [row["relative_path"].rsplit("/", 1)[-1]
                                                    for row in runtime._manifest("fp8-scaled")["models"][:2]]
    assert result["comfy_main_pid"] == 1694 and result["comfy_invocation_id"] == "a" * 32
    assert result["fp8_inference_verified"] is False and result["real_video_generated"] is False
    assert result["full_hash_recomputed_this_boot"] is False


@pytest.mark.parametrize("failure", ["old_audit", "fp8_audit", "old_process", "old_receipt", "selection"])
def test_fp8_rejects_stale_or_mismatched_profile_evidence(monkeypatch, failure):
    runtime = module(monkeypatch)
    scripts = written_files(runtime.build_cached_start_commands(profile="fp8-scaled"))
    with monkeypatch.context() as patch:
        stored, _, _, _ = environment(runtime, patch, profile="fp8-scaled")
        if failure in {"old_audit", "fp8_audit"}:
            name = "verified-models.json" if failure == "old_audit" else "verified-models-fp8-scaled.json"
            stored[BASE + "/" + name] += b"\n"
            with pytest.raises(AssertionError):
                execute_generated(scripts[BASE + "/verify-retained-cache-fp8-scaled.py"])
            return
        execute_generated(scripts[BASE + "/verify-retained-cache-fp8-scaled.py"])
        if failure == "old_process":
            stored["/proc/1694/environ"] = b"ANIFLOW_WAN_PROFILE=fp16"
        elif failure == "old_receipt":
            receipt = json.loads(stored[BASE + "/cached-restore-verification-fp8-scaled.json"])
            receipt["profile"] = "fp16"
            stored[BASE + "/cached-restore-verification-fp8-scaled.json"] = json.dumps(receipt).encode()
        else:
            selection = json.loads(stored[BASE + "/workflow-bundle-fp8-scaled.json"])
            selection["prompt"]["3"]["inputs"]["unet_name"] = "old-fp16.safetensors"
            stored[BASE + "/workflow-bundle-fp8-scaled.json"] = json.dumps(selection).encode()
        before = list(sys.path)
        try:
            with pytest.raises(AssertionError):
                execute_generated(scripts[BASE + "/capture-cached-runtime-fp8-scaled.py"])
        finally:
            sys.path[:] = before


@pytest.mark.parametrize("profile", [None, "fp8", "gguf", "unknown"])
def test_unknown_runtime_profile_is_rejected(monkeypatch, profile):
    runtime = module(monkeypatch)
    for builder in (runtime._manifest, runtime.build_cached_start_commands,
                    runtime.build_runtime_capture_commands):
        with pytest.raises(ValueError, match="Unknown Wan"):
            builder(profile=profile)


def test_fp8_nvme_experts_use_extra_paths_while_t5_and_vae_stay_on_root(monkeypatch, capsys):
    runtime = module(monkeypatch)
    selected = runtime.FP8_NVME_MODELS_ROOT
    commands = runtime.build_cached_start_commands(profile="fp8-scaled", models_root=selected)
    scripts = written_files(commands)
    yaml_path = BASE + "/extra-model-paths-fp8-scaled.yaml"
    assert "diffusion_models: diffusion_models" in scripts[yaml_path]
    assert "text_encoders" not in scripts[yaml_path] and "vae:" not in scripts[yaml_path]
    assert "--extra-model-paths-config " + yaml_path in scripts["/etc/systemd/system/aniflow-comfy.service"]
    assert "ANIFLOW_EXPECTED_EXPERT_ROOT=" + selected in runtime.build_runtime_capture_commands(
        profile="fp8-scaled", models_root=selected)[-1]
    with monkeypatch.context() as patch:
        stored, sizes, _, _ = environment(runtime, patch, profile="fp8-scaled", models_root=selected)
        assert all(selected + "/" + row["relative_path"] in sizes
                   for row in runtime._manifest("fp8-scaled")["models"][:2])
        assert all(BASE + "/ComfyUI/models/" + row["relative_path"] in sizes
                   for row in runtime._manifest("fp8-scaled")["models"][2:])
        execute_generated(scripts[BASE + "/verify-retained-cache-fp8-scaled.py"])
        before = list(sys.path)
        try:
            execute_generated(scripts[BASE + "/capture-cached-runtime-fp8-scaled.py"])
        finally:
            sys.path[:] = before
        receipt = json.loads(stored[BASE + "/cached-restore-verification-fp8-scaled.json"])
        assert receipt["physical_layout_verified"] and receipt["expert_models_root"] == selected
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["expert_models_root"] == selected and result["process_profile_verified"]


def test_fp8_nvme_cache_rejects_same_named_root_expert_that_would_shadow_it(monkeypatch):
    runtime = module(monkeypatch)
    scripts = written_files(runtime.build_cached_start_commands(
        profile="fp8-scaled", models_root=runtime.FP8_NVME_MODELS_ROOT))
    with monkeypatch.context() as patch:
        _, sizes, _, _ = environment(runtime, patch, profile="fp8-scaled",
                                     models_root=runtime.FP8_NVME_MODELS_ROOT)
        row = runtime._manifest("fp8-scaled")["models"][0]
        sizes[BASE + "/ComfyUI/models/" + row["relative_path"]] = row["bytes"]
        with pytest.raises(AssertionError, match="shadow"):
            execute_generated(scripts[BASE + "/verify-retained-cache-fp8-scaled.py"])


@pytest.mark.parametrize("failure", ["boot", "deadline", "root", "hash_proof", "symlink"])
def test_fp8_physical_layout_must_match_current_boot_deadline_and_verified_files(monkeypatch, failure):
    runtime = module(monkeypatch)
    scripts = written_files(runtime.build_cached_start_commands(profile="fp8-scaled"))
    with monkeypatch.context() as patch:
        stored, _, links, _ = environment(runtime, patch, profile="fp8-scaled")
        path = BASE + "/physical-layout-fp8-scaled.json"
        layout = json.loads(stored[path])
        if failure == "boot":
            layout["boot_id"] = "old-boot"
        elif failure == "deadline":
            layout["deadline_utc"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        elif failure == "root":
            layout["expert_models_root"] = runtime.FP8_NVME_MODELS_ROOT
        elif failure == "hash_proof":
            layout["expert_files_sha256_verified"] = False
        else:
            links.add(runtime.DEFAULT_MODELS_ROOT)
        stored[path] = json.dumps(layout).encode()
        with pytest.raises(AssertionError):
            execute_generated(scripts[BASE + "/verify-retained-cache-fp8-scaled.py"])
        assert BASE + "/cached-restore-verification-fp8-scaled.json" not in stored


@pytest.mark.parametrize("models_root", ["/tmp/models", "/mnt/aniflow-fp8/models/../bad", "/mnt/aniflow-fp8/models/", []])
def test_unapproved_model_root_is_rejected_before_commands(monkeypatch, models_root):
    runtime = module(monkeypatch)
    for builder in (runtime.build_cached_start_commands, runtime.build_runtime_capture_commands):
        with pytest.raises(ValueError, match="Unapproved Wan"):
            builder(profile="fp8-scaled", models_root=models_root)
        with pytest.raises(ValueError, match="Unapproved Wan"):
            builder(profile="fp16", models_root=runtime.FP8_NVME_MODELS_ROOT)
