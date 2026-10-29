"""Build guarded FP8 staging commands without executing AWS or disk operations."""
import base64
import hashlib
import json
import re
import shlex

from wan_bootstrap import COMFY_COMMIT, MODELS, WEIGHT_REVISION, validate_bundle
from wan_fp8 import FP8_MODELS, MANIFEST_FILENAME, build_bundle, build_manifest

RESERVE_BYTES = 8 * 1024 ** 3
REQUIRED_NEW_BYTES = sum(row[1] for row in FP8_MODELS[:2])
ROOT = "/opt/aniflow/wan"


def _command(source, python="/usr/bin/python3"):
    encoded = base64.b64encode(source.encode()).decode()
    return (shlex.quote(python) + " -c " + shlex.quote(
        "import base64;exec(compile(base64.b64decode(" + repr(encoded)
        + "),'<aniflow-fp8>','exec'))"))


def build_disk_probe_commands():
    """Read space and device identities only; this is not admission evidence until run."""
    return ["set -euo pipefail", _command(_PROBE)]


def build_fp8_copy_commands(*, bucket, object_keys, expected_owner, bundle=None,
                            allow_instance_store=False):
    """Copy only new experts onto the existing root filesystem after fresh checks.

    The caller must separately obtain pre-start space evidence and arm protection.
    Instance-store fallback requires explicit approval plus live identity/blank checks.
    This builder does not start ComfyUI or submit a prompt.
    """
    if (not isinstance(bucket, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
            or not isinstance(expected_owner, str) or not re.fullmatch(r"[0-9]{12}", expected_owner)):
        raise ValueError("Expected a private S3 bucket and explicit account owner")
    if (not isinstance(object_keys, (list, tuple)) or len(object_keys) != 2
            or any(not isinstance(key, str) for key in object_keys)
            or len(set(object_keys)) != 2 or any(not key
                or key.startswith("/") or ".." in key.split("/")
                or any(ord(char) < 32 for char in key) for key in object_keys)):
        raise ValueError("Expected two distinct exact S3 object keys")
    bundle = build_bundle() if bundle is None else bundle
    validate_bundle(bundle, profile="fp8-scaled")
    original = {"schema_version": 1, "comfyui_commit": COMFY_COMMIT,
                "repository": "Comfy-Org/Wan-2.2", "revision": WEIGHT_REVISION,
                "expected_total_bytes": sum(row[1] for row in MODELS),
                "models": [{"relative_path": path, "bytes": size, "sha256": digest,
                            "verified": True} for path, size, digest in MODELS],
                "real_video_generated": False}
    manifest = build_manifest()
    manifest["models"] = [{**row, "verified": True} for row in manifest["models"]]
    manifest["real_video_generated"] = False
    if not isinstance(allow_instance_store, bool):
        raise TypeError("Instance-store permission must be explicit")
    config = {"bucket": bucket, "object_keys": list(object_keys), "owner": expected_owner,
              "original_sha256": hashlib.sha256(json.dumps(original, indent=2).encode()).hexdigest(),
              "manifest": manifest, "manifest_filename": MANIFEST_FILENAME,
              "bundle": bundle, "reserve_bytes": RESERVE_BYTES,
              "allow_instance_store": allow_instance_store}
    source = _COPY.replace("@@CONFIG@@", repr(json.dumps(config)))
    return ["set -euo pipefail", "umask 077", 'test "$(id -u)" -eq 0',
            _command(source, ROOT + "/venv/bin/python"), "sync"]


_PROBE = r'''import json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
root=Path('/opt/aniflow/wan/ComfyUI/models').resolve(strict=True)
space=os.statvfs(root)
def collect(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=20,check=True)
    return json.loads(result.stdout)
data={'schema_version':1,'observed_at_utc':datetime.now(timezone.utc).isoformat(),
    'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'models_root':str(root),'free_bytes':space.f_bavail*space.f_frsize,
    'required_new_bytes':28589485664,'reserve_bytes':8589934592,
    'mount':collect(['findmnt','--json','--target',str(root)]),
    'devices':collect(['lsblk','--json','--bytes','--output',
        'NAME,PATH,TYPE,SIZE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL,PKNAME']),
    'read_only':True,'disk_approved':False,'format_performed':False}
print(json.dumps(data))
'''

_COPY = r'''import hashlib,json,os,re,stat,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
import boto3
from botocore.config import Config
cfg=json.loads(@@CONFIG@@)
root=Path('/opt/aniflow/wan')
models=root/'ComfyUI/models'
assert models.resolve(strict=True)==models and not models.is_symlink()
assert os.stat(models).st_dev==os.stat('/').st_dev,'Only the existing root disk is approved'
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
last_check=0.0
armed_stop=None
def deadline():
    global last_check,armed_stop
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
    if armed_stop is None or time.monotonic()-last_check>=10:
        subprocess.run(['systemctl','is-active','--quiet','aniflow-deadline.service'],check=True,timeout=10)
        journal=subprocess.check_output(['journalctl','-u','aniflow-deadline.service','-b','--no-pager','-o','cat'],text=True,timeout=10)
        markers=re.findall(r'WAN_DEADLINE_ARMED:([^\s]+)',journal)
        assert markers,'Current boot deadline is absent'
        current=datetime.fromisoformat(markers[-1])
        assert armed_stop is None or current==armed_stop,'Deadline changed during copy'
        armed_stop=current
        last_check=time.monotonic()
    assert armed_stop.tzinfo is not None and 0<(armed_stop-datetime.now(timezone.utc)).total_seconds()<=14400
    return armed_stop.isoformat()
stop=deadline()
original=(root/'verified-models.json').read_bytes()
assert hashlib.sha256(original).hexdigest()==cfg['original_sha256'],'Original FP16 audit changed'
old=json.loads(original)
for row in old['models']:
    path=models/row['relative_path']
    assert path.resolve(strict=True)==path and path.is_file() and path.stat().st_size==row['bytes']
assert subprocess.check_output(['git','-C',str(root/'ComfyUI'),'rev-parse','HEAD'],text=True,timeout=10).strip()==cfg['manifest']['comfyui_commit']
new_rows=cfg['manifest']['models'][:2]
missing=sum(row['bytes'] for row in new_rows if not (models/row['relative_path']).exists())
space=os.statvfs(models)
placement={'kind':'existing-root','device':None,'formatted':False}
expert_models=models
def run_json(args):
    return json.loads(subprocess.check_output(args,text=True,timeout=20))
def blank_instance_store():
    devices=run_json(['lsblk','--json','--bytes','--output',
        'NAME,PATH,TYPE,SIZE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL,PKNAME,RO,MAJ:MIN'])['blockdevices']
    candidates=[row for row in devices if str(row.get('model','')).strip()=='Amazon EC2 NVMe Instance Storage']
    assert len(candidates)==1,'Expected exactly one AWS instance-store device'
    row=candidates[0]
    device=row['path']
    assert re.fullmatch(r'/dev/nvme[0-9]+n1',device)
    assert row['type']=='disk' and not row.get('pkname') and not row.get('children')
    assert not row.get('fstype') and not any(row.get('mountpoints') or []) and not row['ro']
    assert 240000000000<=int(row['size'])<=260000000000,'Not the approved 250GB instance store'
    identity=os.stat(device)
    assert stat.S_ISBLK(identity.st_mode) and identity.st_rdev!=os.stat('/').st_dev
    for name in ('holders','slaves'):
        assert not list((Path('/sys/class/block')/Path(device).name/name).iterdir())
    probe=subprocess.run(['blkid','-p','-o','export',device],capture_output=True,text=True,timeout=20)
    assert probe.returncode==2 and not probe.stdout.strip() and not probe.stderr.strip(),'Device has a signature or unreadable probe'
    signatures=run_json(['wipefs','--no-act','--json',device])
    assert signatures.get('signatures')==[],'Device contains signatures'
    return row,identity.st_rdev
if space.f_bavail*space.f_frsize<missing+cfg['reserve_bytes']:
    assert cfg.get('allow_instance_store') is True,'Insufficient root disk space'
    assert not any((models/row['relative_path']).exists() for row in new_rows),'Root FP8 files would shadow instance-store experts'
    mount=Path('/mnt/aniflow-fp8')
    assert mount.parent.resolve(strict=True)==mount.parent and not mount.is_symlink()
    assert not mount.exists() or (mount.is_dir() and not mount.is_mount() and not list(mount.iterdir()))
    before,identity=blank_instance_store()
    assert deadline()==stop
    again,current_identity=blank_instance_store()
    assert before==again and identity==current_identity,'Disk identity changed before format'
    assert deadline()==stop
    intent=root/('fp8-instance-store-format-intent-'+boot+'.json')
    with intent.open('x') as stream:
        json.dump({'boot_id':boot,'deadline_utc':stop,'device':before,
            'device_identity':identity,'root_device':os.stat('/').st_dev,
            'blank_signature_probes':True,'disk_identity_rechecked_before_format':True,
            'original_fp16_manifest_preserved':True},stream,indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    subprocess.run(['mkfs.ext4','-q','-L','aniflow-fp8',before['path']],check=True,timeout=90,capture_output=True,text=True)
    mount.mkdir(exist_ok=True)
    subprocess.run(['mount','-o','nodev,nosuid,noexec',before['path'],str(mount)],check=True,timeout=20,capture_output=True,text=True)
    assert mount.is_mount() and os.stat(mount).st_dev==identity
    expert_models=mount/'models'
    expert_models.mkdir()
    (expert_models/'diffusion_models').mkdir()
    space=os.statvfs(expert_models)
    assert space.f_bavail*space.f_frsize>=sum(row['bytes'] for row in new_rows)+cfg['reserve_bytes']
    placement={'kind':'aws-instance-store','device':before,'formatted':True,
        'blank_signature_probes':True,'disk_identity_rechecked_before_format':True}
client=boto3.client('s3',region_name='us-east-2',config=Config(connect_timeout=10,read_timeout=30,retries={'max_attempts':1}))
def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(8*1024*1024):
            assert deadline()==stop
            value.update(chunk)
    return value.hexdigest()
for row,key in zip(new_rows,cfg['object_keys']):
    assert deadline()==stop
    target=expert_models/row['relative_path']
    assert target.parent.resolve(strict=True)==target.parent and not target.is_symlink()
    if not target.exists():
        head=client.head_object(Bucket=cfg['bucket'],Key=key,ExpectedBucketOwner=cfg['owner'])
        assert head['ContentLength']==row['bytes'] and head.get('ServerSideEncryption')=='AES256'
        partial=target.with_name(target.name+'.'+boot+'.part')
        response=client.get_object(Bucket=cfg['bucket'],Key=key,ExpectedBucketOwner=cfg['owner'])
        assert response['ContentLength']==row['bytes']
        value=hashlib.sha256()
        count=0
        try:
            with partial.open('xb') as stream:
                while chunk:=response['Body'].read(8*1024*1024):
                    assert deadline()==stop
                    count+=len(chunk)
                    assert count<=row['bytes']
                    stream.write(chunk)
                    value.update(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            response['Body'].close()
        assert count==row['bytes'] and value.hexdigest()==row['sha256'],'FP8 source hash mismatch'
        assert digest(partial)==row['sha256'],'FP8 written file hash mismatch'
        assert not target.exists() and not target.is_symlink()
        partial.rename(target)
    else:
        assert target.is_file() and target.stat().st_size==row['bytes'] and digest(target)==row['sha256']
    assert target.stat().st_size==row['bytes']
space=os.statvfs(expert_models)
assert space.f_bavail*space.f_frsize>=cfg['reserve_bytes'],'FP8 staging consumed safety reserve'
assert deadline()==stop and (root/'verified-models.json').read_bytes()==original
def write_new(path,text):
    assert not path.is_symlink()
    if path.exists():
        assert path.read_text()==text,'Existing FP8 evidence differs; do not overwrite'
    else:
        with path.open('x') as stream:stream.write(text)
write_new(root/cfg['manifest_filename'],json.dumps(cfg['manifest'],indent=2))
write_new(root/'workflow-bundle-fp8-scaled.json',json.dumps(cfg['bundle'],indent=2))
layout={'schema_version':1,'profile':'fp8-scaled','expert_models_root':str(expert_models),
    'boot_id':boot,'deadline_utc':stop,'expert_files_sha256_verified':True,
    'placement':placement,'original_fp16_manifest_preserved':True}
layout_path=root/'physical-layout-fp8-scaled.json'
assert not layout_path.is_symlink()
if layout_path.exists():assert json.loads(layout_path.read_text()).get('profile')=='fp8-scaled'
layout_temp=root/('physical-layout-fp8-scaled.'+boot+'.tmp')
with layout_temp.open('x') as stream:stream.write(json.dumps(layout,indent=2))
layout_temp.replace(layout_path)
print(json.dumps({'schema_version':1,'profile':'fp8-scaled','boot_id':boot,'stop_utc':stop,
    'verified_new_expert_count':2,'verified_new_expert_bytes':sum(row['bytes'] for row in new_rows),
    'original_fp16_manifest_preserved':True,'reused_t5_vae_original_audit':True,
    'new_experts_full_hash_verified':True,'manifest_filename':cfg['manifest_filename'],
    'expert_models_root':str(expert_models),'placement':placement,
    'comfy_started':False,'model_inference_verified':False,'real_video_generated':False}))
'''
