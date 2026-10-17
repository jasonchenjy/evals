"""Exercise the exact live image/adapter with FAKE auth; never invoke a model."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

from common import ROOT, adapter_hashes, save
sys.path.append(str(ROOT))
from environment import PilotEnvironment
from codex_agent import PilotCodex
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


async def main(args):
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
            config={'web_search':'disabled'},extra_env={'CODEX_AUTH_JSON_PATH':str(fakeauth)})
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
        await env.freeze()
        save(args.output/'summary.json',dict(passed=True,model_calls=0,real_auth_used=False,
             adapter_hashes=adapter_hashes(),native_launch_preparation=agent.preparation_observed,
             native_model_command_blocked=True,native_fake_auth_cleanup=True,
             codex_version=version.stdout.strip(),fake_auth_readable_by_candidate=True,
             network='public; arbitrary candidate shells share Codex connectivity',management_tcp=json.loads(api.stdout)))
    finally:
        await env.stop(True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--endpoint',default='unix:///private/tmp/pytest5786-colima/default/docker.sock')
    a=p.parse_args();a.task=a.task.resolve();a.output=a.output.resolve()
    os.environ.update(DOCKER_HOST=a.endpoint,DOCKER_CONFIG=str(ROOT/'tools/docker'),HOME=str(ROOT/'tools/home'),PYTHONDONTWRITEBYTECODE='1')
    asyncio.run(main(a))
