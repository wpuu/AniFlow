import ast
import base64
import builtins
import copy
import importlib.util
import json
import re
import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]


def module():
    spec = importlib.util.spec_from_file_location("wan_bootstrap", ROOT / "infra/ec2/wan_bootstrap.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def bundle():
    return json.loads((ROOT / "infra/ec2/wan-workflow-bundle.template.json").read_text(encoding="utf-8"))


def test_generation_is_pure_and_never_runs_network_or_subprocess(monkeypatch):
    network = Mock(side_effect=AssertionError("No network is allowed"))
    process = Mock(side_effect=AssertionError("No subprocess is allowed"))
    monkeypatch.setattr("socket.socket", network)
    monkeypatch.setattr("subprocess.run", process)
    bootstrap = module()
    data = bundle()
    before = copy.deepcopy(data)
    assert bootstrap.build_bootstrap(data).startswith("#!/bin/bash\nset -euo pipefail\n")
    assert data == before
    network.assert_not_called()
    process.assert_not_called()


def test_manifest_locks_four_original_models_revision_sizes_and_sha256():
    bootstrap = module()
    manifest = bootstrap.validate_bundle(bundle())
    assert manifest["comfyui_commit"] == "63be2f9b82ad0dac88a7ceaa28a9cf3154125a18"
    assert manifest["revision"] == "ee6f4a40737a995bf5818954cfce6d59443b0f04"
    assert manifest["repository"] == "Comfy-Org/Wan-2.2"
    assert manifest["expected_total_bytes"] == 68776044287
    assert len(manifest["models"]) == 4
    assert all(re.fullmatch("[a-f0-9]{64}", row["sha256"]) for row in manifest["models"])
    assert [(row["relative_path"], row["bytes"], row["sha256"]) for row in manifest["models"]] == list(bootstrap.MODELS)


@pytest.mark.parametrize("field,value", [
    ("comfyui_commit", "0" * 40), ("weight_revision", "main"),
    ("weight_repository", "untrusted/wan"),
])
def test_changed_source_pins_are_rejected(field, value):
    data = bundle()
    data["preparation"][field] = value
    with pytest.raises(ValueError, match="pinned FP16"):
        module().build_bootstrap(data)


@pytest.mark.parametrize("field,value", [
    ("relative_path", "../../other.safetensors"), ("sha256", "0" * 64), ("bytes", 1),
])
def test_changed_weight_manifest_is_rejected(field, value):
    data = bundle()
    data["preparation"]["models"][0][field] = value
    with pytest.raises(ValueError, match="pinned FP16"):
        module().build_bootstrap(data)


@pytest.mark.parametrize("node,field,value", [
    ("3", "weight_dtype", "fp8_e4m3fn"), ("5", "device", "cpu"),
    ("11", "width", 640), ("11", "height", 640), ("11", "length", 81),
    ("12", "steps", 4), ("13", "steps", 4), ("13", "start_at_step", 2),
    ("12", "cfg", 1), ("9", "shift", 1), ("15", "fps", 16),
])
def test_reduced_precision_or_quality_or_cpu_inference_is_rejected(node, field, value):
    data = bundle()
    data["prompt"][node]["inputs"][field] = value
    with pytest.raises(ValueError, match="pinned FP16"):
        module().build_bootstrap(data)


def test_extra_or_substituted_nodes_are_rejected():
    for changed in ("extra", "substitute"):
        data = bundle()
        if changed == "extra":
            data["prompt"]["17"] = {"class_type": "SomeCustomCPUNode", "inputs": {}}
        else:
            data["prompt"]["14"]["class_type"] = "SomeCustomCPUNode"
        with pytest.raises(ValueError, match="pinned FP16"):
            module().build_bootstrap(data)


@pytest.mark.parametrize("data", [None, {}, {"preparation": {}}, {"prompt": []}])
def test_incomplete_bundle_is_rejected(data):
    with pytest.raises(ValueError, match="pinned FP16"):
        module().build_bootstrap(data)


def test_launch_is_loopback_default_dynamic_vram_mmap_without_precision_fallback():
    script = module().build_bootstrap(bundle())
    line = next(row for row in script.splitlines() if row.startswith("exec /opt/aniflow/wan/venv"))
    assert shlex.split(line) == ["exec", "/opt/aniflow/wan/venv/bin/python", "main.py",
                                 "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"]
    for flag in ("--highvram", "--lowvram", "--cpu", "--cpu-vae", "--gpu-only",
                 "--disable-dynamic-vram", "--disable-mmap", "--fp8", "0.0.0.0"):
        assert flag not in script
    assert "CPU inference is forbidden" in script
    assert "'dynamic_vram_verified': False" in script
    assert "'real_video_generated': False" in script


def test_dlami_torch_is_reused_and_versions_and_source_are_checked():
    script = module().build_bootstrap(bundle())
    assert "BASE=/opt/pytorch/bin/python" in script
    assert '"$BASE" -m venv --system-site-packages' in script
    assert "dlami-readonly.pth" in script
    assert "--constraint" in script and "requirements-preserve-torch.txt" in script
    assert "{'torch', 'torchvision', 'torchaudio'}" in script
    assert "== base['torch_file']" in script
    assert "importlib.metadata.version(name) == version" in script
    for option in ("--upgrade", "--force-reinstall", "--ignore-installed"):
        assert option not in script


def test_https_sources_pins_ffmpeg_and_complete_model_verification():
    script = module().build_bootstrap(bundle())
    assert "https://github.com/Comfy-Org/ComfyUI.git" in script
    assert "checkout --detach -q " + module().COMFY_COMMIT in script
    assert "--index-url https://pypi.org/simple" in script
    assert "deb https://archive.ubuntu.com/ubuntu" in script
    assert "deb https://security.ubuntu.com/ubuntu" in script
    assert "ffmpeg -version" in script and "ffprobe -version" in script
    assert "https://huggingface.co/" in script
    assert "'--proto', '=https', '--proto-redir', '=https'" in script
    assert "digest(partial) == row['sha256']" in script
    assert "digest(target) == row['sha256']" in script
    assert "'verified': True" in script
    assert "verified-models.json" in script
    assert "docker" not in script.lower()
    assert "/prompt" not in script


def test_heredoc_python_is_valid_without_literal_backslash_newlines():
    script = module().build_bootstrap(bundle())
    sections = re.findall(r"<<'(ANIFLOW_\w+)'\n(.*?)\n\1", script, re.DOTALL)
    python = {name: text for name, text in sections if name in {
        "ANIFLOW_BASE", "ANIFLOW_REQUIREMENTS", "ANIFLOW_RUNTIME", "ANIFLOW_MODELS"}}
    assert len(python) == 4
    for name, text in python.items():
        compile(text, name, "exec")
    literals = [node.value for text in python.values() for node in ast.walk(ast.parse(text))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert "\\n" not in literals


def test_embedded_python_writes_real_line_separators_to_constraints_pth_and_requirements():
    script = module().build_bootstrap(bundle())
    sections = dict(re.findall(r"<<'(ANIFLOW_\w+)'\n(.*?)\n\1", script, re.DOTALL))
    written = {}
    versions = {"torch": "2.11.0+cu130", "torchvision": "0.26.0+cu130",
                "torchaudio": "2.11.0+cu130"}

    class MemoryPath(str):
        def __truediv__(self, part):
            return MemoryPath(str(self).rstrip("/") + "/" + str(part))

        def resolve(self):
            return self

        def is_relative_to(self, other):
            return self.startswith(str(other).rstrip("/") + "/")

        def glob(self, pattern):
            assert self == "/opt/aniflow/wan/venv/lib"
            assert pattern == "python*/site-packages"
            return iter([MemoryPath(str(self) + "/python3.13/site-packages")])

        def write_text(self, value):
            written[str(self)] = value
            return len(value)

        def read_text(self):
            assert self == "/opt/aniflow/wan/ComfyUI/requirements.txt"
            return "torch>=2.9\ntorchvision\ntorchaudio>=2.9\ntorchsde\nnumpy>=1.25\n"

    fake_torch = SimpleNamespace(__file__="/opt/pytorch/lib/python3.13/site-packages/torch/__init__.py",
                                 cuda=SimpleNamespace(is_available=lambda: True,
                                                      device_count=lambda: 1))

    def local_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pathlib":
            return SimpleNamespace(Path=MemoryPath)
        if name == "torch":
            return fake_torch
        if name == "importlib.metadata":
            return SimpleNamespace(metadata=SimpleNamespace(version=versions.__getitem__))
        if name == "sysconfig":
            return SimpleNamespace(get_path=lambda name: "/opt/pytorch/lib/python3.13/site-packages")
        return builtins.__import__(name, globals, locals, fromlist, level)

    namespace = {"__builtins__": {**vars(builtins), "__import__": local_import}}
    for name in ("ANIFLOW_BASE", "ANIFLOW_REQUIREMENTS"):
        exec(compile(sections[name], name, "exec"), namespace)  # noqa: S102 -- Constant code, in-memory paths.
    constraints = written["/opt/aniflow/wan/torch-constraints.txt"]
    pth = written["/opt/aniflow/wan/venv/lib/python3.13/site-packages/dlami-readonly.pth"]
    requirements = written["/opt/aniflow/wan/requirements-preserve-torch.txt"]
    assert constraints == "".join(name + "==" + version + "\n" for name, version in versions.items())
    assert pth == "/opt/pytorch/lib/python3.13/site-packages\n"
    assert requirements == "torchsde\nnumpy>=1.25\n"
    for value in (constraints, pth, requirements):
        assert value.encode().endswith(bytes([10]))
        assert bytes([92, 110]) not in value.encode()


def test_last_shell_status_uses_echo_without_an_escaped_format_string():
    script = module().build_bootstrap(bundle())
    assert shlex.split(script.strip().splitlines()[-1]) == [
        "echo", "BOOTSTRAP_PREPARED_NOT_COMFY_READY"]


def test_bundle_and_manifest_are_encoded_without_shell_interpretation():
    data = bundle()
    injection = "ANIFLOW_RUNTIME\n$(touch /tmp/unwanted)\n'\""
    data["prompt"]["7"]["inputs"]["text"] = injection
    script = module().build_bootstrap(data)
    assert injection not in script and "$(touch" not in script
    rows = re.findall(r"printf '%s' '([A-Za-z0-9+/=]+)' \| base64 -d > \"\$ROOT/([^\"]+)\"", script)
    decoded = {name: json.loads(base64.b64decode(value)) for value, name in rows}
    assert decoded["workflow-bundle.json"] == data
    assert decoded["pinned-models.json"] == module().validate_bundle(data)
