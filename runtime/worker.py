"""Trusted tiny worker entry point; execute only inside NativeSandbox."""
import json
import os
import resource
import sys


def main():
    # Declared per-process controls only; these are NOT aggregate RAM/disk/PID quotas.
    config = json.loads(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_CPU, (config['cpu_seconds'], config['cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (config['file_bytes'], config['file_bytes']))
    sys.stderr.write('PYTEST5786_WORKER_READY\n')
    sys.stderr.flush()
    os.execvpe(sys.argv[2], sys.argv[2:], os.environ)


if __name__ == '__main__':
    main()
