"""Trusted image-independent -I bootstrap executed as root, after Agent return.

Only the controller can exec as root. Candidate uid=1000 has no capabilities,
no-new-privileges and no writable executable runtime. PID 1 is trusted sleep.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time


def candidate_pids():
    found = []
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit():
            try:
                # /proc directory ownership can become root when a nonroot
                # process disables dumpability. Read kernel-reported UIDs.
                uids = (proc / 'status').read_text().split('Uid:')[1].splitlines()[0].split()
                if '1000' in uids:
                    found.append(int(proc.name))
            except FileNotFoundError:
                pass
    return found


if '--source-only' not in sys.argv:
    deadline = time.monotonic() + 5
    while True:
        pids = candidate_pids()
        # Stop every live descendant before killing, so it cannot continue forking.
        for pid in pids:
            try:
                os.kill(pid, signal.SIGSTOP)
            except ProcessLookupError:
                pass
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        live = []
        for pid in candidate_pids():
            try:
                state = Path('/proc', str(pid), 'status').read_text().split('State:')[1].splitlines()[0]
                if 'Z' not in state:
                    live.append(pid)
            except FileNotFoundError:
                pass
        if not live:
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Candidate processes did not stop")
        time.sleep(.01)


if '--quiesce-only' in sys.argv:
    print(json.dumps(dict(candidate_processes_stopped=True)))
    raise SystemExit(0)

root = Path('/work/src')
assert root.is_dir() and not root.is_symlink()
files, total, count = {}, 0, 0
for current, dirs, names in os.walk(root, followlinks=False):
    for name in dirs + names:
        p = Path(current) / name
        s = p.lstat()
        count += 1
        assert count <= 10000
        assert stat.S_ISDIR(s.st_mode) or (stat.S_ISREG(s.st_mode) and s.st_nlink == 1), str(p)
        if stat.S_ISREG(s.st_mode):
            total += s.st_size
            assert s.st_size <= 2*1024*1024 and total <= 16*1024*1024
            if p.suffix == '.py':
                files[str(p.relative_to('/work'))] = dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), bytes=s.st_size, mode=stat.S_IMODE(s.st_mode))
print(json.dumps(dict(candidate_processes_stopped=True, source=files)))
