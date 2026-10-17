"""Exercise the exact live image/adapter with FAKE auth; never invoke a model."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

from common import ROOT, REPO, adapter_hashes, task_hashes, validate_task, load_runtime, save
from snapshot import normalize_git_modes
sys.path.append(str(ROOT))
from environment import PilotEnvironment
from codex_agent import PilotCodex, pilot_config
from harbor.models.task.config import EnvironmentConfig, NetworkPolicy
from harbor.models.trial.paths import TrialPaths
from harbor.models.agent.context import AgentContext
from run import public_gate


class ModelInvocationBlocked(RuntimeError):
    pass


class PreflightCodex(PilotCodex):
    """Exercise native run preparation but never execute its model command."""
    reached_model_command = False

    async def exec_as_agent(self, environment, command, **kwargs):
        if 'codex exec ' in command:
            self.reached_model_command = True
            program = '''import json,os,stat
from pathlib import Path
home=Path(os.environ['CODEX_HOME'])
config=home/'config.toml'
auth=home/'auth.json'
assert auth.read_text()=='FAKE_AUTHENTICATION_CANARY'
assert config.stat().st_uid==1000 and stat.S_IMODE(config.stat().st_mode)==0o600
assert 'web_search = "disabled"' in config.read_text()
assert not (home/'sessions').exists()
print(json.dumps({'native_config_mode':'0600','native_config_owner':1000,'fresh_session':True,'fake_auth_link_readable':True}))
'''
            result = await super().exec_as_agent(environment,
                command='/usr/local/bin/python -I -c '+shlex.quote(program), env=kwargs['env'])
            assert result.return_code==0, 'Native launch preparation check failed'
            self.preparation_observed=json.loads(result.stdout)
            raise ModelInvocationBlocked('Model invocation intentionally blocked by fake-auth preflight')
        return await super().exec_as_agent(environment, command=command, **kwargs)


class ToolPreflightCodex(PilotCodex):
    async def exec_as_agent(self, environment, command, **kwargs):
        if command.startswith('rm -rf '):
            program='''import json,os
from pathlib import Path
root=Path('/home/agent/.codex');v=os.statvfs(root)
files=[]
for p in root.rglob('*'):
 try:
  s=p.lstat();files.append({'path':str(p.relative_to(root)),'bytes':s.st_size,'blocks':s.st_blocks,'mode':s.st_mode})
 except FileNotFoundError: pass
print(json.dumps({'available_bytes':v.f_bavail*v.f_frsize,'total_bytes':v.f_blocks*v.f_frsize,'files':files}))
'''
            result=await environment.exec('/usr/local/bin/python -I -c '+shlex.quote(program))
            if result.return_code==0:
                save(self.logs_dir.parent/'home-usage.json',json.loads(result.stdout))
        return await super().exec_as_agent(environment,command=command,**kwargs)


async def main(args):
    code_hashes=adapter_hashes()
    Package,_,_,collect,assert_applied=load_runtime()
    package=Package(REPO/'pytest_5786',REPO.parent/'pytest')
    validate_task(args.task,package)
    inputs = task_hashes(args.task)
    args.output.mkdir(parents=True, exist_ok=False)
    paths=TrialPaths(trial_dir=args.output)
    env=PilotEnvironment(environment_dir=args.task/'environment',environment_name='pilot-live-preflight',
        session_id='live-preflight',trial_paths=paths,
        task_env_config=EnvironmentConfig(cpus=2,memory_mb=4096,network_mode='public'),
        network_policy=NetworkPolicy(network_mode='public'))
    try:
        await env.start(False)
        fake=args.output/'host-fake-private';fake.write_text('FAKE_PRIVATE_CANARY')
        trial=SimpleNamespace(agent_environment=env,paths=paths,
            task=SimpleNamespace(paths=SimpleNamespace(environment_dir=args.task/'environment')))
        await public_gate(trial,json.loads((args.task/'provenance.json').read_text()),[str(fake)])
        fakeauth=args.output/'fake-auth.txt';fakeauth.write_text('FAKE_AUTHENTICATION_CANARY')
        agent=PreflightCodex(logs_dir=args.output/'agent',model_name='openai/gpt-6.1-sol',version='0.162.1',
            config=pilot_config(),extra_env={'CODEX_AUTH_JSON_PATH':str(fakeauth)})
        await agent.setup(env)
        version=await env.exec('codex --version',user='1000:1000')
        assert version.return_code==0 and '0.162.1' in version.stdout
        remote=str(agent._REMOTE_CODEX_SECRETS_DIR/'auth.json')
        result=await env.exec('mkdir -p '+shlex.quote(str(agent._REMOTE_CODEX_SECRETS_DIR)),user='1000:1000')
        assert result.return_code==0
        # Only synthetic content is uploaded. This is NOT a real login test.
        await env.upload_file(fakeauth,remote)
        await agent.exec_as_root(env,'chown '+env.default_user+' '+remote)
        result=await env.exec('/usr/local/bin/python -I -c '+shlex.quote(
            'from pathlib import Path;assert Path('+repr(remote)+').read_text()=="FAKE_AUTHENTICATION_CANARY";print("same_uid_auth_readable")'),user='1000:1000')
        assert result.return_code==0
        try:
            await agent.run('Fake-auth launch preflight; never call a model.',env,AgentContext())
        except ModelInvocationBlocked:
            pass
        else:
            raise RuntimeError('Native preparation did not reach the guarded model boundary')
        assert agent.reached_model_command
        cleanup=await env.exec('test ! -e '+shlex.quote(str(agent._REMOTE_CODEX_HOME))+
            ' && test ! -e '+shlex.quote(str(agent._REMOTE_CODEX_SECRETS_DIR)),user='1000:1000')
        assert cleanup.return_code==0, 'Native fake-auth cleanup failed'
        # Probe container-management TCP ports only, not arbitrary host services.
        network='''import json,socket,struct
from pathlib import Path
gateways=[socket.inet_ntoa(struct.pack('<I',int(row.split()[2],16))) for row in Path('/proc/net/route').read_text().splitlines()[1:] if row.split()[1]=='00000000']
r={}
for host in gateways:
 for port in [2375,2376]:
  s=socket.socket();s.settimeout(1)
  try:s.connect((host,port));r[str(port)]='reachable'
  except OSError:r[str(port)]='unreachable'
  finally:s.close()
print(json.dumps(r));assert r and all(v=='unreachable' for v in r.values())
'''
        api=await env.exec('/usr/local/bin/python -I -c '+shlex.quote(network),user='1000:1000')
        assert api.return_code==0, api.stdout
        # Exercise the native Harbor run with a local deterministic provider.
        # No inference, real credentials, issue-solving prompt or upstream proxy.
        await env.upload_file(Path(__file__).with_name('tool_fixture.py'), '/tmp/tool_fixture.py')
        started=await env.exec('nohup /usr/local/bin/python -I /tmp/tool_fixture.py > /tmp/fixture.log 2>&1 &')
        assert started.return_code==0
        for _ in range(20):
            ready=await env.exec('test -f /tmp/fixture-ready')
            if ready.return_code==0: break
            await asyncio.sleep(.1)
        assert ready.return_code==0
        fixture_config=pilot_config()
        fixture_config.update(model_provider='offline_fixture',model_providers={'offline_fixture':{
            'name':'Offline fixture','base_url':'http://127.0.0.1:8765','wire_api':'responses',
            'requires_openai_auth':False,'request_max_retries':0,'stream_max_retries':0}})
        fixture_config['features']['enable_request_compression']=False
        fixture_agent=ToolPreflightCodex(logs_dir=args.output/'tools-agent',model_name='openai/gpt-6.1-sol',
            version='0.162.1',config=fixture_config,extra_env={'CODEX_AUTH_JSON_PATH':str(fakeauth)})
        await fixture_agent.setup(env)
        await asyncio.wait_for(fixture_agent.run('Offline tool preflight. Only a disposable probe; no benchmark task.',env,AgentContext()),120)
        await env.freeze()
        log=(env.evidence/'logs/agent/codex.txt').read_text()
        events=[]
        for line in log.splitlines():
            try: events.append(json.loads(line))
            except ValueError: pass
        items=[e['item'] for e in events if e.get('type')=='item.completed']
        commands=[i for i in items if i['type']=='command_execution']
        assert len(commands)==6 and [i['exit_code'] for i in commands]==[0,0,0,0,0,7], commands
        assert any(i['type']=='file_change' and i['status']=='completed' for i in items)
        assert log.count('PINNED_ENV_OK')>=3 and 'PUBLIC_AND_XDIST_OK' in log and 'PTY_DONE' in log
        fixture=json.loads((env.evidence/'logs/agent/offline-fixture.json').read_text())
        assert fixture['requests']==8
        home=json.loads((args.output/'home-usage.json').read_text())
        assert home['available_bytes']>32*1024*1024
        assert not any('plugins-clone' in x['path'] for x in home['files'])
        save(args.output/'tool-preflight.json',dict(passed=True,real_model_calls=0,local_fixture_requests=8,
            default_and_nonlogin_python=True,public_tests_expected_failures=2,xdist_workers=2,
            native_apply_patch=True,pty_resume=True,nonzero_exit_preserved=True))
        # Use the same frozen source collector and fresh-base apply as production.
        Package,_,_,collect,assert_applied=load_runtime()
        package=Package(REPO/'pytest_5786',REPO.parent/'pytest')
        normalize_git_modes(env.captured,args.task/'environment/base')
        provenance=json.loads((args.task/'provenance.json').read_text())
        record=collect(package,env.captured,provenance['baseline'],args.output/'submission')
        assert record['status']=='accepted'
        fresh=args.output/'independent-apply';package.prepare(fresh)
        patch=args.output/'submission/submission.patch'
        assert_applied(package,patch,fresh,record['source_sha256'])
        assert (fresh/'src/harbor_tool_probe.py').read_text()=='VALUE = 2\n'
        verifier=PilotEnvironment(environment_dir=args.task/'tests',environment_name='pilot-roundtrip-verifier',
            session_id='roundtrip__verifier__check',trial_paths=paths,
            task_env_config=EnvironmentConfig(cpus=2,memory_mb=4096,network_mode='no-network'),
            network_policy=NetworkPolicy(network_mode='no-network'))
        try:
            await verifier.start(False)
            await verifier.upload_file(patch,'/tmp/submission.patch')
            applied=await verifier.exec('git apply --whitespace=nowarn /tmp/submission.patch && python -c '+shlex.quote(
                'from pathlib import Path;assert Path("/work/src/harbor_tool_probe.py").read_text()=="VALUE = 2\\n";print("ROUNDTRIP_OK")'))
            assert applied.return_code==0,applied.stdout
            await verifier.freeze()
            assert json.loads((verifier.evidence/'handoff.json').read_text())['source']==json.loads((env.evidence/'handoff.json').read_text())['source']
        finally:
            await verifier.stop(True)
        save(args.output/'roundtrip.json',dict(passed=True,separate_verifier=True,exact_source_inventory=True,
             patch_sha256=__import__('hashlib').sha256(patch.read_bytes()).hexdigest()))
        assert task_hashes(args.task)==inputs
        assert adapter_hashes()==code_hashes, 'Adapter changed during preflight'
        save(args.output/'summary.json',dict(passed=True,model_calls=0,real_auth_used=False,
             task_hashes=inputs,tool_preflight_passed=True,artifact_roundtrip_passed=True,
             adapter_hashes=code_hashes,native_launch_preparation=agent.preparation_observed,
             native_model_command_blocked=True,native_fake_auth_cleanup=True,
             codex_version=version.stdout.strip(),fake_auth_readable_by_candidate=True,
             network='public; arbitrary candidate shells share Codex connectivity',management_tcp=json.loads(api.stdout)))
    finally:
        try:
            if getattr(env,'cid',None) and not getattr(env,'frozen',False):
                await env.freeze()
        finally:
            await env.stop(True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--endpoint',default='unix:///private/tmp/pytest5786-colima/default/docker.sock')
    a=p.parse_args();a.task=a.task.resolve();a.output=a.output.resolve()
    os.environ.update(DOCKER_HOST=a.endpoint,DOCKER_CONFIG=str(ROOT/'tools/docker'),HOME=str(ROOT/'tools/home'),PYTHONDONTWRITEBYTECODE='1')
    asyncio.run(main(a))
