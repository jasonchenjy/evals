"""Harmless worker probe. All outside paths must be controller-created fake files."""
import errno
import json
import os
from pathlib import Path
import socket
import resource
import subprocess
import sys


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    results = {}
    work = Path.cwd()
    def check(name, fn, denied=False):
        try:
            fn()
            results[name] = {"passed": not denied, "operation": "allowed"}
        except OSError as exc:
            results[name] = {"passed": denied and exc.errno in (errno.EPERM, errno.EACCES),
                             "operation": "denied" if exc.errno in (errno.EPERM, errno.EACCES) else "error",
                             "errno": exc.errno, "error": str(exc)}
        except Exception as exc:
            detail = getattr(exc, "stderr", b"")
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", "replace")
            results[name] = {"passed": False, "operation": "error", "error": str(exc), "stderr": detail}
    check("workspace_write", lambda: (Path(os.environ["EVAL_SCRATCH"]) / "own.txt").write_text("canary"))
    check("workspace_read", lambda: (work / "src/_pytest/reports.py").read_bytes())
    def edit_source():
        path = work / 'src/_pytest/runtime_canary_edit.py'
        path.write_text('# harmless source edit probe\n')
        assert path.read_text() == '# harmless source edit probe\n'
        path.unlink()
    check('source_edit', edit_source)
    for name in ("private", "other_trial", "shared_tmp", "credentials"):
        check(name, lambda name=name: Path(config[name]).read_bytes(), True)
    check("relative_private", lambda: Path(os.path.relpath(config["private"], work)).read_bytes(), True)
    check("outside_write", lambda: Path(config["outside_write"]).write_text("unexpected"), True)
    check("dependencies", lambda: __import__("pkg_resources"))
    check("historical_import", lambda: __import__("pytest"))
    if config.get('git_checks', True):
        check("git_status", lambda: subprocess.run([config.get("git", "/usr/bin/git"), "status", "--porcelain"], check=True, capture_output=True))
        check("git_diff", lambda: subprocess.run([config.get("git", "/usr/bin/git"), "diff", "--stat"], check=True, capture_output=True))
        check("git_write_protected", lambda: (work / ".git/canary-write").write_text("unexpected"), True)
    if config.get('readonly_canary'):
        check('immutable_input_read', lambda: Path(config['readonly_canary']).read_bytes())
        check('immutable_input_write', lambda: Path(config['readonly_canary']).write_text('unexpected'), True)
    def network():
        with socket.socket() as sock:
            sock.settimeout(2)
            sock.connect(("1.1.1.1", 443))  # TCP only; never transmit contents or credentials.
    check("network", network, True)
    def ipc():
        a, b = socket.socketpair()
        a.close()
        b.close()
    check("local_ipc", ipc)
    if config.get('limited_worker'):
        def limits():
            assert resource.getrlimit(resource.RLIMIT_CPU) == (30, 30)
            assert resource.getrlimit(resource.RLIMIT_FSIZE) == (32*1024*1024, 32*1024*1024)
        check('per_process_limits', limits)
    print(json.dumps(results, indent=2))
    return 0 if all(item["passed"] for item in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
