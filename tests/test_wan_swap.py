import base64
import builtins
import importlib.util
import io
import json
import os
import shlex
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]
SIZE = 64 * 1024**3
TARGET = "/swapfile-aniflow"
LINE = TARGET + " none swap sw 0 0\n"


def module():
    spec = importlib.util.spec_from_file_location("wan_swap", ROOT / "infra/ec2/wan_swap.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    return runtime


def environment():
    runtime = module()
    state = SimpleNamespace(files={}, descriptors={}, writes=[], active=False, unknown_swap=False,
                            free=70 * 1024**3, signature=False, swap_bytes=SIZE - 4096,
                            deadline=True, next_fd=10)

    class File(io.StringIO):
        def __init__(self, path, descriptor):
            self.path, self.descriptor = path, descriptor
            super().__init__(state.files[path].get("text", ""))

        def write(self, text):
            state.writes.append(self.path)
            result = super().write(text)
            state.files[self.path]["text"] = self.getvalue()
            return result

        def fileno(self):
            return self.descriptor

    def info(path):
        row = state.files[path]
        return SimpleNamespace(st_mode=row.get("mode", stat.S_IFREG | 0o600), st_nlink=1,
                               st_uid=0, st_dev=1, st_ino=row.get("inode", 10),
                               st_size=row.get("size", 0), st_blocks=row.get("size", 0) // 512)

    def open_file(path, flags, mode=0o600):
        if flags & os.O_CREAT:
            if path in state.files:
                raise FileExistsError(path)
            state.files[path] = {"mode": stat.S_IFREG | mode, "size": 0}
            state.writes.append(path)
        state.next_fd += 1
        state.descriptors[state.next_fd] = path
        return state.next_fd

    def allocate(descriptor, offset, size):
        assert offset == 0
        state.files[state.descriptors[descriptor]]["size"] = size

    def read_text(path):
        if path == "/proc/sys/kernel/random/boot_id":
            return "current-boot\n"
        if path == "/proc/meminfo":
            return f"MemTotal: 16000000 kB\nSwapTotal: {state.swap_bytes // 1024 if state.active else 0} kB\n"
        if path == "/proc/swaps":
            target = "/unknown" if state.unknown_swap else TARGET
            return "Filename Type Size Used Priority\n" + (
                f"{target} file {state.swap_bytes // 1024} 0 -2\n" if state.active else "")
        return state.files[path]["text"]

    def run(args, **kwargs):
        assert kwargs["check"] is True
        if args[0] == "systemctl":
            assert state.deadline, "Inactive deadline"
        elif args[0] == "mkswap":
            assert kwargs["capture_output"] is True and kwargs["text"] is True
            state.signature = True
        elif args[0] == "swapon":
            state.active = True
        else:
            raise AssertionError(args)

    def output(args, **kwargs):
        if args[0] == "journalctl":
            return "prefix\nWAN_DEADLINE_ARMED:" + (
                datetime.now(UTC) + timedelta(hours=1)).isoformat() + "\nsuffix\n"
        assert args[0] == "blkid"
        return "TYPE=swap\nLABEL=aniflow-wan\nUUID=known-uuid\n" if state.signature else ""

    state.files["/etc/fstab"] = {"text": "# Original comment\nUUID=root / ext4 defaults 0 1"}
    fake_os = SimpleNamespace(**{name: getattr(os, name, 0x20000000) for name in (
        "O_RDWR", "O_NOFOLLOW", "O_CREAT", "O_EXCL", "O_WRONLY")})
    fake_os.geteuid = lambda: 0
    fake_os.path = SimpleNamespace(lexists=lambda path: path in state.files)
    fake_os.lstat = info
    fake_os.stat = lambda path: SimpleNamespace(st_dev=1)
    fake_os.statvfs = lambda path: SimpleNamespace(f_bavail=state.free // 4096, f_frsize=4096)
    fake_os.open = open_file
    fake_os.fdopen = lambda descriptor, mode: File(state.descriptors[descriptor], descriptor)
    fake_os.fchmod = lambda descriptor, mode: None
    fake_os.posix_fallocate = Mock(side_effect=allocate)
    fake_os.fsync = lambda descriptor: None
    fake_os.close = lambda descriptor: None
    process = SimpleNamespace(run=Mock(side_effect=run), check_output=Mock(side_effect=output))
    replacements = {"os": fake_os, "subprocess": process,
                    "pathlib": SimpleNamespace(Path=lambda path: SimpleNamespace(
                        read_text=lambda: read_text(path))),
                    "fcntl": SimpleNamespace(LOCK_EX=2, flock=lambda descriptor, mode: None)}

    def importer(name, *args, **kwargs):
        return replacements.get(name) or builtins.__import__(name, *args, **kwargs)

    namespace = {"__builtins__": dict(vars(builtins), __import__=importer)}
    exec(runtime._SCRIPT.rsplit("configure()", 1)[0], namespace)  # noqa: S102
    return state, namespace["configure"], fake_os, process


def test_commands_only_build_guarded_local_script(monkeypatch):
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError))
    runtime = module()
    commands = runtime.build_swap_commands()
    assert commands[3] == "systemctl is-active --quiet aniflow-deadline.service"
    assert base64.b64decode(shlex.split(commands[-1])[2]).decode() == runtime._SCRIPT
    compile(runtime._SCRIPT, "swap.py", "exec")
    for forbidden in ("swapoff", "unlink", "truncate", "pip install", "curl", "/prompt",
                      "swappiness", "--cpu", "--fp8", "boto3", "resize2fs"):
        assert forbidden not in runtime._SCRIPT
    assert runtime.SWAP_EXECUTION_TIMEOUT_SECONDS == 600


def test_new_swap_is_allocated_verified_and_fstab_appended_once(capsys):
    state, configure, fake_os, process = environment()
    original = state.files["/etc/fstab"]["text"]
    configure()
    report = json.loads(capsys.readouterr().out)
    assert report["swap_active"] is True and report["swap_reused"] is False
    assert report["effective_swap_bytes"] == SIZE - 4096
    assert report["boot_id"] == "current-boot"
    assert report["physical_ram_unchanged"] is True and report["cache_only"] is True
    assert report["model_devices_changed"] is False and report["precision_changed"] is False
    assert report["real_video_generated"] is False
    fake_os.posix_fallocate.assert_called_once()
    assert state.files["/etc/fstab"]["text"] == original + "\n" + LINE
    calls = [call.args[0][0] for call in process.run.call_args_list]
    assert calls.count("mkswap") == 1 and calls.count("swapon") == 1
    configure()
    reused = json.loads(capsys.readouterr().out)
    assert reused["swap_reused"] is True
    assert state.files["/etc/fstab"]["text"] == original + "\n" + LINE
    assert fake_os.posix_fallocate.call_count == 1
    assert sum(call.args[0][0] == "mkswap" for call in process.run.call_args_list) == 1
    assert sum(call.args[0][0] == "swapon" for call in process.run.call_args_list) == 1


@pytest.mark.parametrize("case", ["space", "unknown", "symlink", "fstab", "deadline", "active"])
def test_unsafe_initial_state_never_writes(case):
    state, configure, fake_os, process = environment()
    if case == "space":
        state.free = 68 * 1024**3 - 4096
    elif case == "unknown":
        state.files[TARGET] = {"size": SIZE}
    elif case == "symlink":
        state.files[TARGET] = {"mode": stat.S_IFLNK | 0o600}
    elif case == "fstab":
        state.files["/etc/fstab"]["text"] += "\n" + TARGET + " none swap defaults 0 0\n"
    elif case == "deadline":
        state.deadline = False
    else:
        state.active, state.unknown_swap = True, True
    with pytest.raises((AssertionError, KeyError)):
        configure()
    assert state.writes == []
    fake_os.posix_fallocate.assert_not_called()
    assert all(call.args[0][0] not in ("mkswap", "swapon")
               for call in process.run.call_args_list)


def test_bad_effective_swap_never_persists_fstab(capsys):
    state, configure, _, _ = environment()
    original = state.files["/etc/fstab"]["text"]
    state.swap_bytes = SIZE // 2
    with pytest.raises(AssertionError, match="Active swap size mismatch"):
        configure()
    assert state.files["/etc/fstab"]["text"] == original
    assert capsys.readouterr().out == ""


def test_existing_receipt_identity_change_is_rejected_without_overwrite(capsys):
    state, configure, fake_os, _ = environment()
    configure()
    capsys.readouterr()
    state.files[TARGET]["inode"] = 999
    state.writes.clear()
    with pytest.raises(AssertionError, match="Swap identity changed"):
        configure()
    assert state.writes == [] and fake_os.posix_fallocate.call_count == 1


def test_reboot_reuses_known_inactive_swap_without_reformatting(capsys):
    state, configure, fake_os, process = environment()
    configure()
    capsys.readouterr()
    state.active, state.free = False, 1024**3
    process.run.reset_mock()
    state.writes.clear()
    configure()
    assert json.loads(capsys.readouterr().out)["swap_reused"] is True
    assert state.writes == [] and fake_os.posix_fallocate.call_count == 1
    calls = [call.args[0][0] for call in process.run.call_args_list]
    assert "mkswap" not in calls and calls.count("swapon") == 1


def test_allocation_failure_preserves_partial_file_and_never_formats_it():
    state, configure, fake_os, process = environment()
    original = state.files["/etc/fstab"]["text"]
    fake_os.posix_fallocate.side_effect = OSError("Out of space")
    with pytest.raises(OSError, match="Out of space"):
        configure()
    assert TARGET in state.files and state.files["/etc/fstab"]["text"] == original
    assert all(call.args[0][0] not in ("mkswap", "swapon")
               for call in process.run.call_args_list)
    state.writes.clear()
    with pytest.raises(KeyError):
        configure()
    assert state.writes == [] and fake_os.posix_fallocate.call_count == 1


def test_changed_uuid_never_reformats_or_activates_file(capsys):
    state, configure, _, process = environment()
    configure()
    capsys.readouterr()
    state.active, state.signature = False, False
    state.writes.clear()
    process.run.reset_mock()
    with pytest.raises(AssertionError, match="Invalid swap signature"):
        configure()
    assert state.writes == []
    assert all(call.args[0][0] not in ("mkswap", "swapon")
               for call in process.run.call_args_list)
