"""Build guarded root-disk swap commands without executing them."""
import base64
import shlex

SWAP_EXECUTION_TIMEOUT_SECONDS = 600


def build_swap_commands():
    """Return root-run Bash commands; allocation never expands the existing volume."""
    encoded = base64.b64encode(_SCRIPT.encode()).decode()
    return ["set -euo pipefail", "umask 077", 'test "$(id -u)" -eq 0',
            "systemctl is-active --quiet aniflow-deadline.service",
            "printf %s " + shlex.quote(encoded) + " | base64 -d | /usr/bin/python3 -I"]


_SCRIPT = r'''import fcntl,json,os,re,stat,subprocess
from datetime import datetime,timezone
from pathlib import Path

TARGET='/swapfile-aniflow'
RECEIPT=TARGET+'.receipt.json'
SIZE=64*1024**3
LINE=TARGET+' none swap sw 0 0'

def command(*args):
    return subprocess.check_output(args,text=True,timeout=30).strip()

def deadline():
    subprocess.run(['systemctl','is-active','--quiet','aniflow-deadline.service'],check=True,timeout=10)
    journal=command('journalctl','-u','aniflow-deadline.service','-b','--no-pager','-o','cat')
    armed=re.findall(r'WAN_DEADLINE_ARMED:([^\s]+)',journal)
    assert armed, 'Missing current-boot deadline'
    stop=datetime.fromisoformat(armed[-1])
    assert stop.tzinfo is not None and 0 < (stop-datetime.now(timezone.utc)).total_seconds() <= 14400, 'Invalid deadline'

def secure_file(path):
    info=os.lstat(path)
    assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0, 'Unsafe file identity'
    assert stat.S_IMODE(info.st_mode)==0o600, 'Unsafe file permissions'
    return info

def meminfo():
    return {row.split(':',1)[0]:int(row.split()[1])*1024
            for row in Path('/proc/meminfo').read_text().splitlines() if ':' in row}

def swaps():
    rows=[row.split() for row in Path('/proc/swaps').read_text().splitlines()[1:] if row.strip()]
    assert all(len(row)==5 and row[0]==TARGET and row[1]=='file' for row in rows), 'Unknown active swap'
    assert len(rows)<=1, 'Duplicate active swap'
    if rows:
        assert SIZE-1024**2 <= int(rows[0][2])*1024 <= SIZE, 'Active swap size mismatch'
    return rows

def configure():
    assert os.geteuid()==0, 'Root required'
    deadline()
    before=meminfo()
    active=swaps()
    root_device=os.stat('/').st_dev
    with os.fdopen(os.open('/etc/fstab',os.O_RDWR|os.O_NOFOLLOW),'r+') as fstab:
        fcntl.flock(fstab,fcntl.LOCK_EX)
        original=fstab.read()
        entries=[row.split() for row in original.splitlines()
                 if row.strip() and not row.lstrip().startswith('#')]
        matching=[row for row in entries if row[0]==TARGET]
        assert len(matching)<=1 and (not matching or matching[0]==LINE.split()), 'Conflicting fstab entry'
        exists=os.path.lexists(TARGET)
        if exists:
            info=secure_file(TARGET)
            secure_file(RECEIPT)
            receipt=json.loads(Path(RECEIPT).read_text())
            assert receipt['path']==TARGET and receipt['bytes']==SIZE, 'Unknown swap receipt'
            assert (receipt['device'],receipt['inode'])==(info.st_dev,info.st_ino), 'Swap identity changed'
        else:
            assert not active and not os.path.lexists(RECEIPT), 'Orphan swap state'
            free=os.statvfs('/').f_bavail*os.statvfs('/').f_frsize
            assert free>=SIZE+4*1024**3, 'Insufficient root-disk free space; require 68 GiB'
            descriptor=os.open(TARGET,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
            try:
                os.fchmod(descriptor,0o600)
                os.posix_fallocate(descriptor,0,SIZE)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            info=secure_file(TARGET)
        assert info.st_dev==root_device and info.st_size==SIZE, 'Swap must occupy exactly 64 GiB on root disk'
        assert info.st_blocks*512>=SIZE, 'Swap file must be fully allocated'
        if not exists:
            deadline()
            subprocess.run(['mkswap','-L','aniflow-wan',TARGET],check=True,timeout=60,capture_output=True,text=True)
        identity=dict(row.split('=',1) for row in command('blkid','-p','-o','export',TARGET).splitlines() if '=' in row)
        assert identity.get('TYPE')=='swap' and identity.get('LABEL')=='aniflow-wan' and identity.get('UUID'), 'Invalid swap signature'
        if exists:
            assert receipt['uuid']==identity['UUID'], 'Swap UUID changed'
        else:
            receipt={'schema_version':1,'path':TARGET,'bytes':SIZE,'device':info.st_dev,
                     'inode':info.st_ino,'uuid':identity['UUID']}
            with os.fdopen(os.open(RECEIPT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w') as output:
                json.dump(receipt,output)
                output.flush()
                os.fsync(output.fileno())
        deadline()
        if not active:
            subprocess.run(['swapon',TARGET],check=True,timeout=60)
        assert len(swaps())==1, 'Swap not active'
        after=meminfo()
        assert SIZE-1024**2 <= after['SwapTotal'] <= SIZE, 'Effective SwapTotal mismatch'
        assert before['MemTotal']==after['MemTotal'], 'Physical RAM changed'
        current=secure_file(TARGET)
        assert (current.st_dev,current.st_ino,current.st_size)==(info.st_dev,info.st_ino,SIZE), 'Swap identity changed'
        if not matching:
            fstab.seek(0,2)
            fstab.write(('' if not original or original.endswith('\n') else '\n')+LINE+'\n')
            fstab.flush()
            os.fsync(fstab.fileno())
        fstab.seek(0)
        assert sum(row.split()==LINE.split() for row in fstab.read().splitlines())==1, 'Swap fstab readback failed'
    report={'schema_version':1,'observed_at_utc':datetime.now(timezone.utc).isoformat(),
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'swap_path':TARGET,'swap_file_bytes':SIZE,'effective_swap_bytes':after['SwapTotal'],
            'swap_active':True,'swap_on_existing_root_disk':True,'swap_reused':exists,
            'physical_ram_bytes':after['MemTotal'],'physical_ram_unchanged':True,
            'cache_only':True,'purpose':'host_memory_backing_only',
            'model_devices_changed':False,'precision_changed':False,
            'model_inference_verified':False,'real_video_generated':False}
    print(json.dumps(report))

configure()
'''
