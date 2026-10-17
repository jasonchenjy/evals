"""Create an isolated synthetic task using the already verified pilot runtime."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE_COMMIT='adb1b8fe6fd81e25b880f3bdee2adb74e1ca306d'


def git(root,*args):
    env=dict(os.environ,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,
             GIT_AUTHOR_NAME='Harbor preflight',GIT_AUTHOR_EMAIL='preflight@invalid',
             GIT_COMMITTER_NAME='Harbor preflight',GIT_COMMITTER_EMAIL='preflight@invalid',
             GIT_AUTHOR_DATE='2026-01-01T00:00:00Z',GIT_COMMITTER_DATE='2026-01-01T00:00:00Z')
    return subprocess.check_output(['git','-C',str(root),*args],env=env,stderr=subprocess.PIPE)


def build(runtime_task,output,live):
    output.mkdir(parents=True,exist_ok=False)
    for name in ('environment','tests'):
        (output/name).mkdir()
        shutil.copytree(ROOT/'sample_repo',output/name/'base')
        base=output/name/'base'
        git(base,'init','-q','--initial-branch=main')
        git(base,'add','.')
        git(base,'commit','-qm','Fixed coding workflow base')
        commit=git(base,'rev-parse','HEAD').decode().strip()
        assert commit==BASE_COMMIT, 'Synthetic base changed; review and requalify'
        # Reuse the exact already-provisioned runtime, never private task files.
        shutil.copyfile(runtime_task/name/'Dockerfile',output/name/'Dockerfile')
        policy=json.loads((runtime_task/name/'docker-compose.yaml').read_text())
        if not live or name=='tests':policy['services']['main']['network_mode']='none'
        (output/name/'docker-compose.yaml').write_text(json.dumps(policy,indent=2)+'\n')
    shutil.copytree(runtime_task/'environment/codex-bundle',output/'environment/codex-bundle')
    shutil.copyfile(ROOT/'instruction.md',output/'instruction.md')
    config=(runtime_task/'task.toml').read_text().replace('1800.0','300.0')
    config=config.replace('[verifier]\n','[verifier]\nuser = "1000:1000"\n')
    if not live:config=config.replace('network_mode = "public"','network_mode = "no-network"')
    (output/'task.toml').write_text(config)
    (output/'tests/test.sh').write_text('#!/bin/sh\nexit 99 # Supported custom verifier only.\n')
    manifest={str(p.relative_to(output/'environment/base')):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (output/'environment/base').rglob('*') if p.is_file() and '.git' not in p.parts}
    provenance=dict(baseline=commit,live=live,public_files=manifest,
                    runtime_provenance=json.loads((runtime_task/'provenance.json').read_text()))
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(commit)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime-task',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--live',action='store_true')
    a=p.parse_args();build(a.runtime_task.resolve(),a.output.resolve(),a.live)
