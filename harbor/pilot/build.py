"""Build a public-only Harbor task; no private Eval bytes enter either image."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from common import ROOT, REPO, load_runtime, save


def build(output, image, repo, live=False, codex=None):
    Package, *_ = load_runtime()
    package = Package(REPO / 'pytest_5786', repo)
    output.mkdir(parents=True, exist_ok=False)
    for name in ('environment', 'tests'):
        (output / name).mkdir()
    baseline = package.prepare(output / 'environment/base')
    shutil.copyfile(package.root / 'instruction.md', output / 'instruction.md')
    network = 'public' if live else 'no-network'
    (output / 'task.toml').write_text(f'''schema_version = "1.4"
artifacts = []
[agent]
user = "1000:1000"
timeout_sec = 1800.0
[environment]
cpus = 2
memory_mb = 4096
network_mode = "{network}"
[verifier]
environment_mode = "separate"
timeout_sec = 1800.0
[verifier.environment]
cpus = 2
memory_mb = 4096
network_mode = "no-network"
''')
    dockerfile = f'''FROM harbor-pilot-base:{image.removeprefix('sha256:')}
COPY base /base
WORKDIR /work
ENV PATH=/opt/pytest-python/bin:$PATH PYTHONPATH=/work/src HOME=/home/agent
RUN mkdir -p /home/agent /work /logs /installed-agent && chmod -R a+rX /base
'''
    if live:
        if codex is None or not codex.is_file():
            raise ValueError('Explicit preprovisioned Linux Codex binary required')
        shutil.copyfile(codex, output / 'environment/codex')
        (output / 'environment/codex').chmod(0o755)
        dockerfile += 'COPY codex /usr/local/bin/codex\n'
    (output / 'environment/Dockerfile').write_text(dockerfile)
    # A real separate Harbor verifier container remains public-only. The custom
    # BaseVerifier delegates candidate execution to restricted sibling workers.
    shutil.copytree(output / 'environment/base', output / 'tests/base')
    (output / 'tests/Dockerfile').write_text(dockerfile.split('COPY codex')[0])
    (output / 'tests/test.sh').write_text('#!/bin/sh\nexit 99 # Only the trusted custom verifier may grade.\n')
    for name, mode in [('environment', network), ('tests', 'no-network')]:
        compose = {'services': {'main': {
            'user': '0:0', 'init': True, 'read_only': True,
            'cap_drop': ['ALL'], 'cap_add': ['KILL'],
            'security_opt': ['no-new-privileges'], 'pids_limit': 128,
            'mem_limit': '4g', 'memswap_limit': '4g', 'cpus': 2,
            'network_mode': 'none' if mode == 'no-network' else 'bridge',
            'tmpfs': ['/work:rw,nosuid,nodev,size=1536m,mode=755,uid=1000,gid=1000',
                      '/tmp:rw,nosuid,nodev,size=256m,mode=1777',
                      '/logs:rw,nosuid,nodev,size=128m,mode=777',
                      '/home/agent:rw,nosuid,nodev,size=64m,mode=755,uid=1000,gid=1000'],
            'shm_size': '16m', 'ulimits': {'fsize': 33554432},
            'logging': {'driver': 'none'},
        }}}
        save(output / name / 'docker-compose.yaml', compose)  # JSON is valid YAML.
    provenance = dict(package.provenance, baseline=baseline, image=image, live=live,
                      instruction_sha256=hashlib.sha256((output/'instruction.md').read_bytes()).hexdigest())
    if live:
        provenance['codex_binary_sha256'] = hashlib.sha256(codex.read_bytes()).hexdigest()
    save(output / 'provenance.json', provenance)
    return provenance


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image', required=True)
    p.add_argument('--repo', type=Path, default=REPO.parent / 'pytest')
    p.add_argument('--live', action='store_true')
    p.add_argument('--codex', type=Path)
    a = p.parse_args()
    build(a.output.resolve(), a.image, a.repo.resolve(), a.live, a.codex)
