"""Seven Harbor controls or one explicitly approved Codex pilot; never auto-retry."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from common import ROOT, REPO, adapter_hashes, task_hashes, validate_task, docker, load_runtime, save
from snapshot import normalize_git_modes

# Load our adapters by unique import names; do not shadow the installed package.
sys.path.insert(0, str(ROOT))
from harbor.models.trial.config import TrialConfig, TaskConfig, AgentConfig, EnvironmentConfig, VerifierConfig
from harbor.trial.trial import Trial
from harbor.trial.hooks import TrialEvent
import environment as pilot_environment
import verifier as pilot_verifier
import controls as pilot_controls
import codex_agent as pilot_codex
sys.modules['pilot_environment'] = pilot_environment
sys.modules['pilot_verifier'] = pilot_verifier
sys.modules['pilot_controls'] = pilot_controls
sys.modules['pilot_codex'] = pilot_codex


async def public_gate(trial, provenance, canaries):
    env = trial.agent_environment
    manifest = {str(p.relative_to(trial.task.paths.environment_dir / 'base')): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (trial.task.paths.environment_dir / 'base').rglob('*') if p.is_file() and '.git' not in p.parts}
    program = '''import hashlib,json,os,pathlib,socket,subprocess,sys
expected=json.loads(sys.argv[1]); canaries=json.loads(sys.argv[2]); root=pathlib.Path('/work')
actual={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}
assert actual==expected
r={'public_payload_exact':True,'uid_nonroot':os.getuid()==1000}
status=pathlib.Path('/proc/self/status').read_text()
r['effective_caps_zero']=int(status.split('CapEff:')[1].splitlines()[0].strip(),16)==0
r['no_new_privileges']='NoNewPrivs:\\t1' in status
try: os.setuid(0)
except PermissionError: r['setuid_denied']=True
else: r['setuid_denied']=False
r['private_paths_absent']=all(not pathlib.Path(p).exists() for p in ['/tests','/eval','/private','/var/run/docker.sock','/run/docker.sock'])
r['host_canaries_absent']=all(not pathlib.Path(p).exists() for p in canaries)
r['cgroup']={n:pathlib.Path('/sys/fs/cgroup',n).read_text().strip() for n in ['cpu.max','memory.max','memory.swap.max','pids.max']}
r['base']=subprocess.check_output(['git','rev-parse','HEAD'],cwd='/work',text=True).strip()
assert all(v for k,v in r.items() if k not in ['cgroup','base'])
assert r['cgroup']['memory.max']=='4294967296' and r['cgroup']['pids.max']=='128'
assert r['cgroup']['memory.swap.max']=='0'
s=socket.socket();s.settimeout(2)
try: s.connect(('1.1.1.1',443));r['external_tcp']='connected'
except OSError as e: r['external_tcp']='blocked';r['network_errno']=e.errno
finally:s.close()
print(json.dumps(r))
'''
    result = await env.exec(command='/usr/local/bin/python -I -c ' + shlex.quote(program) + ' ' +
                            shlex.quote(json.dumps(manifest)) + ' ' + shlex.quote(json.dumps(canaries)), user='1000:1000')
    if result.return_code:
        raise RuntimeError('Agent public/isolation gate failed: ' + result.stdout[-1000:])
    observed = json.loads(result.stdout)
    assert observed['base'] == provenance['baseline']
    if not provenance['live']:
        assert observed['external_tcp'] == 'blocked'
    save(trial.paths.trial_dir / 'agent-gate.json', observed)
    for p in canaries:
        assert Path(p).read_text() == 'FAKE_PRIVATE_CANARY'


async def run(args):
    code_hashes = adapter_hashes()
    Package, _, _, collect, _ = load_runtime()
    package = Package(REPO / 'pytest_5786', args.repo)
    provenance = validate_task(args.task,package)
    assert provenance['image'] == args.image
    # BuildKit requires a tag/reference in FROM, unlike the legacy builder.
    tag = 'harbor-pilot-base:' + args.image.removeprefix('sha256:')
    subprocess.run(docker('tag', args.image, tag), check=True)
    assert subprocess.check_output(docker('image','inspect',tag,'--format','{{.Id}}'), text=True).strip() == args.image
    assert importlib.metadata.version('harbor') == '0.24.0', 'Requalify changed Harbor APIs'
    if args.live:
        if not (provenance['live'] and args.auth_file and args.model and args.approve_container_credentials and args.approve_public_network and args.qualification and args.security and args.preflight and args.worker_checks):
            raise ValueError('Live execution requires model, auth file, passing qualification and both explicit exposure approvals')
        q = json.loads((args.qualification / 'summary.json').read_text())
        assert q['qualification_passed'] and q['check_count'] == 91
        assert q['runtime_hashes'] == json.loads((Path(__file__).parent/'runtime-lock.json').read_text())
        assert q['adapter_hashes'] == code_hashes, 'Adapter changed since qualification'
        assert q['image'] == args.image
        assert json.loads((args.security/'summary.json').read_text())['passed']
        assert json.loads((args.worker_checks/'results.json').read_text())['status']=='PASSED'
        preflight = json.loads((args.preflight/'summary.json').read_text())
        assert preflight['passed'] and preflight['model_calls']==0 and not preflight['real_auth_used']
        assert preflight.get('native_model_command_blocked') and preflight.get('native_fake_auth_cleanup')
        assert preflight.get('adapter_hashes') == code_hashes, 'Preflight must exercise current native launch preparation'
        assert preflight.get('task_hashes') == task_hashes(args.task), 'Generated task or CLI bundle changed since preflight'
        assert preflight.get('tool_preflight_passed') and preflight.get('artifact_roundtrip_passed')
        assert args.auth_file.is_file()
        # One live attempt per output; creation precedes any model/auth operations.
        controls = ['codex']
    else:
        assert not provenance['live']
        controls = ['noop','historical','complete','alternative','last_only','testreport_only','text_only']
    args.output.mkdir(parents=True, exist_ok=False)
    canaries = []
    for name in ['host-private','host-credentials','other-trial']:
        p = args.output / 'canaries' / name
        p.parent.mkdir(exist_ok=True)
        p.write_text('FAKE_PRIVATE_CANARY')
        canaries.append(str(p))
    summary = dict(harbor_version=importlib.metadata.version('harbor'), image=args.image,
                   adapter_hashes=code_hashes,
                   runtime_hashes=json.loads((Path(__file__).parent/'runtime-lock.json').read_text()),
                   model=args.model if args.live else None, live=args.live, controls=[], check_count=0,
                   qualification_passed=False)
    save(args.output / 'summary.json', summary)
    reference = {x['control']: x for x in json.loads((ROOT/'evidence/qualification-comparison.json').read_text())['controls']}
    for name in controls:
        agent = AgentConfig(import_path='pilot_controls:ControlAgent', kwargs={'patch': str(package.root/'private/oracle'/f'{name}.patch')})
        if args.live:
            agent = AgentConfig(import_path='pilot_codex:PilotCodex', model_name=args.model,
                kwargs={'version':'0.162.1', 'config': pilot_codex.pilot_config()},
                env={'CODEX_AUTH_JSON_PATH': str(args.auth_file)})
        cfg = TrialConfig(task=TaskConfig(path=args.task), trial_name=name, trials_dir=args.output,
            agent=agent, environment=EnvironmentConfig(import_path='pilot_environment:PilotEnvironment'),
            verifier=VerifierConfig(import_path='pilot_verifier:IsolatedVerifier',
                                    kwargs={'repo':str(args.repo), 'image':args.image}))
        trial = await Trial.create(cfg)
        async def gate(event):
            await public_gate(trial, provenance, canaries)
        async def freeze(event):
            await trial.agent_environment.freeze()
            if args.live and not getattr(trial.agent_environment,'agent_infrastructure_ok',False):
                raise RuntimeError('Codex did not complete a healthy turn; refusing to grade an infrastructure failure')
            normalize_git_modes(trial.agent_environment.captured, args.task/'environment/base')
            record = collect(package, trial.agent_environment.captured, provenance['baseline'], trial.paths.trial_dir/'submission')
            assert record['status'] == 'accepted'
        trial.add_hook(TrialEvent.AGENT_START, gate)
        trial.add_hook(TrialEvent.AGENT_END, freeze)
        result = await trial.run()
        entry = dict(control=name, exception=result.exception_info.model_dump(mode='json') if result.exception_info else None)
        if entry['exception']:
            entry['infrastructure_status']='agent_or_trial_error'
            entry['expectation_met']=False
            summary['controls'].append(entry)
            summary['live_completed']=False
            save(args.output/'summary.json',summary)
            raise RuntimeError('Trial infrastructure failed; no capability score and no automatic retry')
        path = trial.paths.verifier_dir/'grader/result.json'
        if path.exists():
            actual = json.loads(path.read_text())
            checks = {t['id']:t['status'] for t in actual['tests']}
            dims = {k:v['satisfied'] for k,v in actual['dimensions'].items()}
            entry.update(infrastructure_status=actual['infrastructure_status'], overall=actual['overall_resolved'], checks=checks, dimensions=dims)
            entry['expectation_met'] = (not entry['exception'] and actual['infrastructure_status']=='ok' and
                (args.live or (checks==reference[name]['checks'] and dims==reference[name]['dimensions'] and actual['overall_resolved']==reference[name]['overall'])))
            summary['check_count'] += len(checks)
        else:
            entry['expectation_met'] = False
        summary['controls'].append(entry)
        save(args.output/'summary.json', summary)
        print(json.dumps(entry), flush=True)
        if not entry['expectation_met']:
            raise RuntimeError('Trial failed; no live retry or scoring relaxation')
    summary['qualification_passed'] = not args.live and summary['check_count']==91
    summary['live_completed'] = args.live
    assert adapter_hashes() == code_hashes, 'Adapter changed during execution'
    if args.live:
        save(args.output/'authorization-scope.json', dict(model=args.model, trials=1,
            container_injected_credentials_approved=args.approve_container_credentials,
            public_candidate_network_approved=args.approve_public_network,
            credential_file_path_recorded=False))
    save(args.output/'summary.json', summary)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--repo', type=Path, default=REPO.parent/'pytest')
    p.add_argument('--image', required=True)
    p.add_argument('--endpoint', default='unix:///private/tmp/pytest5786-colima/default/docker.sock')
    p.add_argument('--live', action='store_true')
    p.add_argument('--model')
    p.add_argument('--auth-file', type=Path)
    p.add_argument('--qualification', type=Path)
    p.add_argument('--security', type=Path)
    p.add_argument('--preflight', type=Path)
    p.add_argument('--worker-checks', type=Path)
    p.add_argument('--approve-container-credentials', action='store_true')
    p.add_argument('--approve-public-network', action='store_true')
    a = p.parse_args()
    for key in ('task','output','repo','auth_file','qualification','security','preflight','worker_checks'):
        if getattr(a,key) is not None: setattr(a,key,getattr(a,key).resolve())
    os.environ.update(DOCKER_HOST=a.endpoint, DOCKER_CONFIG=str(ROOT/'tools/docker'),
                      HOME=str(ROOT/'tools/home'), PYTHONDONTWRITEBYTECODE='1')
    asyncio.run(run(a))
