"""Generate, but never execute, the pinned official Wan installation script.

The caller must first verify real GPU admission, the production budget and fixed
shutdown protection. Preparing this script performs no network or AWS operations.
"""
import base64
import json

COMFY_COMMIT = "63be2f9b82ad0dac88a7ceaa28a9cf3154125a18"
WEIGHT_REVISION = "ee6f4a40737a995bf5818954cfce6d59443b0f04"
MODELS = (
    ("diffusion_models/wan2.2_i2v_high_noise_14B_fp16.safetensors", 28577914792,
     "c21c21efa368d529a982a7d89dd11d86608b5937cae9a125d0ffe5491918a100"),
    ("diffusion_models/wan2.2_i2v_low_noise_14B_fp16.safetensors", 28577914792,
     "edb89340c8a6fbf1a70e76a839ae01eaf7d289f05ea1ebd6b1a3fc6f533826e9"),
    ("text_encoders/umt5_xxl_fp16.safetensors", 11366399385,
     "7b8850f1961e1cf8a77cca4c964a358d303f490833c6c087d0cff4b2f99db2af"),
    ("vae/wan_2.1_vae.safetensors", 253815318,
     "2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b"),
)


def validate_bundle(bundle):
    """Fail closed on changes to upstream pins, precision or the approved quality contract."""
    try:
        preparation, prompt = bundle["preparation"], bundle["prompt"]
        rows = preparation["models"]
        actual = [(row["relative_path"], row["bytes"], row["sha256"]) for row in rows]
        valid = (preparation["comfyui_commit"] == COMFY_COMMIT
                 and preparation["weight_repository"] == "Comfy-Org/Wan-2.2"
                 and preparation["weight_revision"] == WEIGHT_REVISION
                 and actual == list(MODELS)
                 and prompt["3"]["inputs"] == {
                     "unet_name": MODELS[0][0].split("/")[-1], "weight_dtype": "default"}
                 and prompt["4"]["inputs"] == {
                     "unet_name": MODELS[1][0].split("/")[-1], "weight_dtype": "default"}
                 and prompt["5"]["inputs"] == {
                     "clip_name": MODELS[2][0].split("/")[-1], "type": "wan", "device": "default"}
                 and prompt["6"]["inputs"]["vae_name"] == MODELS[3][0].split("/")[-1])
        classes = ("LoadImage", "ImageScale", "UNETLoader", "UNETLoader", "CLIPLoader",
                   "VAELoader", "CLIPTextEncode", "CLIPTextEncode", "ModelSamplingSD3",
                   "ModelSamplingSD3", "WanImageToVideo", "KSamplerAdvanced", "KSamplerAdvanced",
                   "VAEDecode", "CreateVideo", "SaveVideo")
        valid = valid and set(prompt) == {str(index) for index in range(1, 17)}
        valid = valid and all(prompt[str(index)]["class_type"] == name
                              for index, name in enumerate(classes, 1))
        for node, expected in {
            "2": {"width": 800, "height": 1376},
            "9": {"shift": 5.0}, "10": {"shift": 5.0},
            "11": {"width": 800, "height": 1376, "length": 121, "batch_size": 1},
            "12": {"steps": 20, "cfg": 3.5, "sampler_name": "euler", "scheduler": "simple",
                   "start_at_step": 0, "end_at_step": 10},
            "13": {"steps": 20, "cfg": 3.5, "sampler_name": "euler", "scheduler": "simple",
                   "start_at_step": 10, "end_at_step": 20},
            "15": {"fps": 24},
        }.items():
            valid = valid and all(prompt[node]["inputs"][key] == value
                                  for key, value in expected.items())
        valid = valid and preparation["final_target"] == {
            "width": 774, "height": 1376, "frames": 120, "fps": 24, "seconds": 5, "crop_x": 13}
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Bundle does not match the pinned FP16 Wan quality contract")
    return {"schema_version": 1, "comfyui_commit": COMFY_COMMIT,
            "repository": "Comfy-Org/Wan-2.2", "revision": WEIGHT_REVISION,
            "expected_total_bytes": sum(row[1] for row in MODELS),
            "models": [{"relative_path": path, "bytes": size, "sha256": digest}
                       for path, size, digest in MODELS]}


def build_bootstrap(bundle):
    """Return a root-run Ubuntu 24.04 script; do not execute it or submit a generation."""
    manifest = validate_bundle(bundle)
    encode = lambda data: base64.b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
    return (_SCRIPT.replace("@@MANIFEST@@", encode(manifest))
            .replace("@@BUNDLE@@", encode(bundle)).replace("@@COMMIT@@", COMFY_COMMIT))


_SCRIPT = r'''#!/bin/bash
set -euo pipefail
umask 077
test "$(id -u)" -eq 0
test "$(uname -m)" = x86_64
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_CODENAME" = noble
ROOT=/opt/aniflow/wan
COMFY="$ROOT/ComfyUI"
BASE=/opt/pytorch/bin/python
PY="$ROOT/venv/bin/python"
test -x "$BASE"
mkdir -p "$ROOT"
exec 9>"$ROOT/bootstrap.lock"
flock -n 9
printf '%s' '@@MANIFEST@@' | base64 -d > "$ROOT/pinned-models.json"
printf '%s' '@@BUNDLE@@' | base64 -d > "$ROOT/workflow-bundle.json"
cat > "$ROOT/ubuntu-https.list" <<'ANIFLOW_APT'
deb https://archive.ubuntu.com/ubuntu noble main universe restricted multiverse
deb https://archive.ubuntu.com/ubuntu noble-updates main universe restricted multiverse
deb https://security.ubuntu.com/ubuntu noble-security main universe restricted multiverse
ANIFLOW_APT
APT=(-o "Dir::Etc::sourcelist=$ROOT/ubuntu-https.list" -o "Dir::Etc::sourceparts=-")
export DEBIAN_FRONTEND=noninteractive
apt-get "${APT[@]}" update -qq
apt-get "${APT[@]}" install -y --no-install-recommends git curl ffmpeg ca-certificates
ffmpeg -version > "$ROOT/ffmpeg-version.txt"
ffprobe -version > "$ROOT/ffprobe-version.txt"
export GIT_TERMINAL_PROMPT=0
if [ ! -d "$COMFY/.git" ]; then
    mkdir -p "$COMFY"
    git -C "$COMFY" init -q
    git -C "$COMFY" remote add origin https://github.com/Comfy-Org/ComfyUI.git
    git -C "$COMFY" fetch --depth=1 origin @@COMMIT@@
    git -C "$COMFY" checkout --detach -q @@COMMIT@@
fi
test "$(git -C "$COMFY" remote get-url origin)" = https://github.com/Comfy-Org/ComfyUI.git
test "$(git -C "$COMFY" rev-parse HEAD)" = @@COMMIT@@
test -z "$(git -C "$COMFY" status --porcelain --untracked-files=no)"
"$BASE" -m venv --system-site-packages "$ROOT/venv"
"$BASE" - <<'ANIFLOW_BASE'
import importlib.metadata
import json
from pathlib import Path
import sysconfig
import torch
root = Path('/opt/aniflow/wan')
assert torch.cuda.is_available() and torch.cuda.device_count() == 1
source = Path(torch.__file__).resolve()
assert source.is_relative_to(Path('/opt/pytorch').resolve())
versions = {name: importlib.metadata.version(name) for name in ('torch', 'torchvision', 'torchaudio')}
(root / 'base-torch.json').write_text(json.dumps({'versions': versions, 'torch_file': str(source)}))
(root / 'torch-constraints.txt').write_text(''.join(name + '==' + version + chr(10) for name, version in versions.items()))
sites = list((root / 'venv/lib').glob('python*/site-packages'))
assert len(sites) == 1
(sites[0] / 'dlami-readonly.pth').write_text(sysconfig.get_path('purelib') + chr(10))
ANIFLOW_BASE
"$PY" - <<'ANIFLOW_REQUIREMENTS'
from pathlib import Path
import re
root = Path('/opt/aniflow/wan')
requirements = (root / 'ComfyUI/requirements.txt').read_text().splitlines()
filtered = [line for line in requirements if re.split(r'[<>=!~;\[\s]', line.strip(), maxsplit=1)[0].lower()
            not in {'torch', 'torchvision', 'torchaudio'}]
(root / 'requirements-preserve-torch.txt').write_text(chr(10).join(filtered) + chr(10))
ANIFLOW_REQUIREMENTS
"$PY" -m pip install --index-url https://pypi.org/simple --constraint "$ROOT/torch-constraints.txt" -r "$ROOT/requirements-preserve-torch.txt"
"$PY" -m pip check
cd "$COMFY"
"$PY" - <<'ANIFLOW_RUNTIME'
import importlib.metadata
import json
from pathlib import Path
import torch
import comfy.model_management as mm
root = Path('/opt/aniflow/wan')
base = json.loads((root / 'base-torch.json').read_text())
assert str(Path(torch.__file__).resolve()) == base['torch_file']
assert all(importlib.metadata.version(name) == version for name, version in base['versions'].items())
assert torch.cuda.is_available() and torch.cuda.device_count() == 1
devices = {'model': str(mm.get_torch_device()), 'text_encoder': str(mm.text_encoder_device()),
           'vae': str(mm.vae_device())}
assert all(device.startswith('cuda') for device in devices.values()), 'CPU inference is forbidden'
(root / 'runtime-prerequisites.json').write_text(json.dumps({
    'torch_file': base['torch_file'], 'versions': base['versions'], 'inference_devices': devices,
    'dynamic_vram_verified': False, 'model_inference_verified': False, 'real_video_generated': False}, indent=2))
ANIFLOW_RUNTIME
"$PY" - <<'ANIFLOW_MODELS'
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
root = Path('/opt/aniflow/wan')
manifest = json.loads((root / 'pinned-models.json').read_text())
models = (root / 'ComfyUI/models').resolve()
models.mkdir(parents=True, exist_ok=True)
def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            value.update(chunk)
    return value.hexdigest()
verified = []
for row in manifest['models']:
    target = models / row['relative_path']
    assert target.resolve().is_relative_to(models) and not target.is_symlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        partial = target.with_suffix(target.suffix + '.part')
        assert not partial.is_symlink()
        offset = partial.stat().st_size if partial.exists() else 0
        assert offset <= row['bytes']
        assert shutil.disk_usage(models).free >= row['bytes'] - offset + 8 * 1024 ** 3
        if offset < row['bytes']:
            url = 'https://huggingface.co/' + manifest['repository'] + '/resolve/' + manifest['revision'] + '/split_files/' + row['relative_path']
            subprocess.run(['curl', '-q', '--proto', '=https', '--proto-redir', '=https',
                '--location', '--fail', '--silent', '--show-error', '--connect-timeout', '15',
                '--max-time', '3600', '--retry', '2', '--continue-at', '-', '--output', str(partial), url],
                check=True, timeout=10900)
        assert partial.stat().st_size == row['bytes'] and digest(partial) == row['sha256']
        partial.replace(target)
    assert target.stat().st_size == row['bytes'] and digest(target) == row['sha256']
    verified.append({**row, 'verified': True})
    print('PINNED_MODEL_VERIFIED:' + row['relative_path'], flush=True)
(root / 'verified-models.json').write_text(json.dumps({**manifest, 'models': verified,
    'real_video_generated': False}, indent=2))
ANIFLOW_MODELS
cat > "$ROOT/start-comfy.sh" <<'ANIFLOW_LAUNCH'
#!/bin/bash
set -euo pipefail
cd /opt/aniflow/wan/ComfyUI
exec /opt/aniflow/wan/venv/bin/python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
ANIFLOW_LAUNCH
chmod 700 "$ROOT/start-comfy.sh"
sync
echo 'BOOTSTRAP_PREPARED_NOT_COMFY_READY'
'''
