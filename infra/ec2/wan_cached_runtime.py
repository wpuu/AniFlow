"""Build cached Wan service commands and fresh evidence; never execute AWS calls."""
import base64
import hashlib
import json
import shlex

from wan_bootstrap import COMFY_COMMIT, MODELS, WEIGHT_REVISION

RUNTIME_CAPTURE_TIMEOUT_SECONDS = 120


def _manifest():
    return {"schema_version": 1, "comfyui_commit": COMFY_COMMIT,
            "repository": "Comfy-Org/Wan-2.2", "revision": WEIGHT_REVISION,
            "expected_total_bytes": sum(row[1] for row in MODELS),
            "models": [{"relative_path": path, "bytes": size, "sha256": digest,
                        "verified": True} for path, size, digest in MODELS],
            "real_video_generated": False}


def _source(script):
    expected = json.dumps(_manifest(), indent=2).encode()
    return script.replace("@@MANIFEST_SHA@@", hashlib.sha256(expected).hexdigest())


def _write(path, text):
    encoded = base64.b64encode(text.encode()).decode()
    return "printf %s " + shlex.quote(encoded) + " | base64 -d > " + shlex.quote(path)


def build_cached_start_commands():
    """Return root-run Bash commands; service startup requires a valid current deadline."""
    return ["set -euo pipefail", "umask 077", 'test "$(id -u)" -eq 0',
            "systemctl is-active --quiet aniflow-deadline.service",
            _write("/opt/aniflow/wan/verify-retained-cache.py", _source(_CACHE_VERIFY)),
            _write("/opt/aniflow/wan/capture-cached-runtime.py", _CAPTURE),
            _write("/etc/systemd/system/aniflow-wan-cache-verify.service", _CACHE_UNIT),
            _write("/etc/systemd/system/aniflow-comfy.service", _COMFY_UNIT),
            "systemctl daemon-reload", "systemctl enable --now aniflow-comfy.service",
            "systemctl is-active --quiet aniflow-comfy.service",
            "systemctl is-enabled --quiet aniflow-comfy.service", "sync"]


def build_runtime_capture_commands():
    """Return read-only collection commands; caller must allow the declared timeout."""
    return ["set -euo pipefail", "cd /opt/aniflow/wan/ComfyUI",
            "/opt/aniflow/wan/venv/bin/python /opt/aniflow/wan/capture-cached-runtime.py"]


_CACHE_UNIT = """[Unit]
Description=Verify retained Wan cache against original hash audit
Requires=aniflow-deadline.service
After=aniflow-deadline.service
Before=aniflow-comfy.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 /opt/aniflow/wan/verify-retained-cache.py
"""

_COMFY_UNIT = """[Unit]
Description=AniFlow pinned cached Wan loopback service
Requires=aniflow-deadline.service aniflow-wan-cache-verify.service
After=network.target aniflow-deadline.service aniflow-wan-cache-verify.service
[Service]
Type=exec
User=root
WorkingDirectory=/opt/aniflow/wan/ComfyUI
ExecStartPre=/usr/bin/systemctl is-active --quiet aniflow-deadline.service
ExecStart=/opt/aniflow/wan/venv/bin/python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
Restart=no
TimeoutStopSec=20
KillMode=control-group
[Install]
WantedBy=multi-user.target
"""

_CACHE_VERIFY = r'''import hashlib,json,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
root=Path('/opt/aniflow/wan')
raw=(root/'verified-models.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='@@MANIFEST_SHA@@', 'Original verified manifest changed'
manifest=json.loads(raw)
assert subprocess.check_output(['git','-C',str(root/'ComfyUI'),'rev-parse','HEAD'],text=True).strip()==manifest['comfyui_commit']
subprocess.run(['systemctl','is-active','--quiet','aniflow-deadline.service'],check=True)
journal=subprocess.check_output(['journalctl','-u','aniflow-deadline.service','-b','--no-pager','-o','cat'],text=True,timeout=10)
armed=re.findall(r'WAN_DEADLINE_ARMED:([^\s]+)',journal)
assert armed
stop=datetime.fromisoformat(armed[-1])
assert stop.tzinfo is not None and 0 < (stop-datetime.now(timezone.utc)).total_seconds() <= 14400
models=(root/'ComfyUI/models').resolve()
for row in manifest['models']:
    path=models/row['relative_path']
    assert path.resolve().is_relative_to(models) and not path.is_symlink() and path.is_file()
    assert row['verified'] is True and path.stat().st_size==row['bytes']
receipt={'schema_version':1,'verified_at_utc':datetime.now(timezone.utc).isoformat(),
    'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'manifest_sha256':hashlib.sha256(raw).hexdigest(),'verified_model_count':len(manifest['models']),
    'cache_restore_verified':True,'full_hash_recomputed_this_boot':False,
    'original_full_hash_audit_preserved':True,'stop_utc':stop.isoformat(),
    'model_inference_verified':False,'real_video_generated':False}
(root/'cached-restore-verification.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
'''

_CAPTURE = r'''import contextlib,hashlib,importlib.metadata,io,json,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import HTTPRedirectHandler,ProxyHandler,build_opener
root=Path('/opt/aniflow/wan')
def command(*args):return subprocess.check_output(args,text=True,timeout=10).strip()
def active(unit):return subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0
def status(unit):
    rows=command('systemctl','show',unit,'-p','Result','-p','ExecMainStatus').splitlines()
    return dict(row.split('=',1) for row in rows)
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,response,code,message,headers,new_url):return None
opener=build_opener(ProxyHandler({}),NoRedirect())
def get(path):
    with opener.open('http://127.0.0.1:8188'+path,timeout=15) as response:
        raw=response.read(8*1024*1024+1)
    assert len(raw)<=8*1024*1024
    return json.loads(raw),hashlib.sha256(raw).hexdigest()
cache=json.loads((root/'cached-restore-verification.json').read_text())
assert cache['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert cache['cache_restore_verified'] is True and cache['verified_model_count']==4
raw=(root/'verified-models.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()==cache['manifest_sha256']
manifest=json.loads(raw)
assert active('aniflow-wan-cache-verify.service') and status('aniflow-wan-cache-verify.service')=={'Result':'success','ExecMainStatus':'0'}
assert active('aniflow-deadline.service') and active('aniflow-comfy.service')
deadline_journal=command('journalctl','-u','aniflow-deadline.service','-b','--no-pager','-o','cat')
armed=re.findall(r'WAN_DEADLINE_ARMED:([^\s]+)',deadline_journal)
assert armed
stop=datetime.fromisoformat(armed[-1])
assert stop.tzinfo is not None and 0 < (stop-datetime.now(timezone.utc)).total_seconds() <=14400
assert stop==datetime.fromisoformat(cache['stop_utc'])
sys.path.insert(0,str(root/'ComfyUI'))
base=json.loads((root/'base-torch.json').read_text())
with contextlib.redirect_stdout(io.StringIO()):
    import torch
    import comfy.model_management as mm
    assert torch.cuda.is_available() and torch.cuda.device_count()==1
    devices={'model':str(mm.get_torch_device()),'text_encoder':str(mm.text_encoder_device()),'vae':str(mm.vae_device())}
assert all(device.startswith('cuda') for device in devices.values())
assert str(Path(torch.__file__).resolve())==base['torch_file']
assert all(importlib.metadata.version(name)==version for name,version in base['versions'].items())
stats,_=get('/system_stats')
schema,schema_sha=get('/object_info')
assert any(device.get('type')=='cuda' for device in stats.get('devices',[]))
classes={'LoadImage','ImageScale','UNETLoader','CLIPLoader','VAELoader','CLIPTextEncode','ModelSamplingSD3','WanImageToVideo','KSamplerAdvanced','VAEDecode','CreateVideo','SaveVideo'}
assert classes.issubset(schema)
for row in manifest['models']:
    node,key=('UNETLoader','unet_name') if row['relative_path'].startswith('diffusion_models/') else (('CLIPLoader','clip_name') if row['relative_path'].startswith('text_encoders/') else ('VAELoader','vae_name'))
    assert Path(row['relative_path']).name in schema[node]['input']['required'][key][0]
log=command('journalctl','-u','aniflow-comfy.service','-b','--no-pager','-o','cat')
log=re.sub(re.escape(chr(27)) + r'\[[0-9;]*m','',log)
dynamic=[line for line in log.splitlines() if 'DynamicVRAM support detected and enabled' in line]
assert dynamic
data={'schema_version':1,'observed_at_utc':datetime.now(timezone.utc).isoformat(),
    'cache_restore_verified':True,'cache_verification':cache,'verified_models':manifest,
    'full_hash_recomputed_this_boot':False,'original_full_hash_audit_preserved':True,
    'comfy_commit':command('git','-C',str(root/'ComfyUI'),'rev-parse','HEAD'),
    'deadline_service_active':True,'deadline_journal':deadline_journal,
    'cache_service_active':True,'comfy_service_active':True,
    'comfy_service_enabled':subprocess.run(['systemctl','is-enabled','--quiet','aniflow-comfy.service']).returncode==0,
    'comfy_log_tail':log[-12000:],'dynamic_vram_enabled_log_lines':dynamic,
    'runtime_prerequisites':{'inference_devices':devices,'torch_file':base['torch_file'],'versions':base['versions']},
    'system_stats':stats,'object_info_sha256':schema_sha,'object_info_required_nodes_present':True,
    'model_choices_verified':True,'model_inference_verified':False,'real_video_generated':False}
assert data['comfy_commit']==manifest['comfyui_commit'] and data['comfy_service_enabled']
print(json.dumps(data))
'''
