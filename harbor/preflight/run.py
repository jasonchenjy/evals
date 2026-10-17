"""Harbor synthetic controls or ONE explicitly authorized native Codex trial."""
import argparse,asyncio,hashlib,importlib.metadata,json,os,shlex,shutil,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'pilot'))
sys.path.insert(1,str(ROOT.parent))
from common import adapter_hashes,task_hashes,save
from environment import PilotEnvironment
from codex_agent import PilotCodex,pilot_config
from snapshot import normalize_git_modes
from run import public_gate
from harbor.agents.nop import NopAgent
from harbor.verifier.base import BaseVerifier
from harbor.models.verifier.result import VerifierResult
from harbor.models.trial.config import TrialConfig,TaskConfig,AgentConfig,EnvironmentConfig,VerifierConfig
from harbor.trial.trial import Trial
from harbor.trial.hooks import TrialEvent
sys.modules['coding_preflight']=sys.modules[__name__]


def code_hashes():
    return dict(adapter=adapter_hashes(),preflight={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts})


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.PIPE,
        env=dict(os.environ,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull))


def source_hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root/'src').rglob('*.py'))}


def collect_source(trial,base):
    captured=trial.agent_environment.captured
    normalize_git_modes(captured,base)
    output=trial.paths.trial_dir/'submission';output.mkdir()
    staged=output/'trusted-workspace';shutil.copytree(base,staged)
    shutil.rmtree(staged/'src');shutil.copytree(captured/'src',staged/'src')
    git(staged,'add','-N','--','src')
    patch=git(staged,'diff','--binary','HEAD','--','src')
    (output/'submission.patch').write_bytes(patch)
    inventory=source_hashes(captured)
    save(output/'submission.json',dict(status='accepted',baseline=git(base,'rev-parse','HEAD').decode().strip(),
         source_sha256=inventory,patch_sha256=hashlib.sha256(patch).hexdigest(),
         candidate_git_used=False,debug_files_excluded=True))


class ScriptedAgent(NopAgent):
    def __init__(self,*args,control,**kwargs):
        super().__init__(*args,**kwargs);self.control=control

    async def setup(self,environment):
        result=await environment.exec('python -c '+shlex.quote(
            'import os,sys;assert sys.executable=="/opt/pytest-python/bin/python";assert sys.version_info[:3]==(3,8,20);assert os.getcwd()=="/work";print(sys.executable,sys.version)'))
        assert result.return_code==0
        (self.logs_dir/'public-preflight.txt').write_text(result.stdout)

    async def run(self,instruction,environment,context):
        records=[]
        async def tests(label,expected):
            result=await environment.exec('python -m unittest discover -s tests -v')
            records.append(dict(stage=label,exit_code=result.return_code,output=result.stdout))
            assert result.return_code==expected,result.stdout
        async def install(files):
            for index,(path,content) in enumerate(files.items()):
                local=self.logs_dir/('source-'+str(index)+'.txt');local.write_text(content)
                await environment.upload_file(local,'/work/'+path)
        await tests('initial failing public test',1)
        if self.control!='noop':
            files=json.loads((ROOT/'private'/('correct.json' if self.control=='complete' else 'incomplete.json')).read_text())
            if self.control=='complete':
                wrong=dict(files);wrong['src/normalization.py']=files['src/normalization.py'].replace("int(order['quantity'])","1")
                await install(wrong)
                await tests('scripted diagnostic wrong edit',1)
            await install(files)
            await tests('final public retest',0)
            status=await environment.exec('git add -N src/normalization.py && git status --short && cat src/normalization.py')
            assert status.return_code==0
            records.append(dict(stage='persistent new and modified source',output=status.stdout))
        if self.control=='complete':
            # Two harmless processes, no resource exhaustion. Child touches only
            # source mtime. Timeout + freeze must terminate both before handoff.
            child="import os,time\nfor _ in range(200):\n os.utime('/work/src/service.py',None);time.sleep(.05)"
            program='import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,"-c",'+repr(child)+'],start_new_session=True);Path("/work/probe-pid").write_text(str(p.pid));Path("/work/debug.tmp").write_text("not source");time.sleep(10)'
            try:
                await environment.exec('/usr/local/bin/python -I -c '+shlex.quote(program),timeout_sec=.5)
            except TimeoutError:
                records.append(dict(stage='bounded command timeout',passed=True))
            else:raise AssertionError('Timeout was not enforced')
        save(self.logs_dir/'diagnostic.json',dict(scripted=True,real_model_calls=0,steps=records))


class SyntheticVerifier(BaseVerifier):
    async def verify(self):
        trial=self.trial_paths.trial_dir
        provenance=json.loads((self.task.paths.environment_dir.parent/'provenance.json').read_text())
        submission=json.loads((trial/'submission/submission.json').read_text())
        env=self.environment
        assert env.default_user=='1000:1000', 'Synthetic checks must execute as the workspace owner'
        before=await env.exec('git rev-parse HEAD && git status --porcelain && test ! -e /tmp/hidden_tests.py')
        save(self.trial_paths.verifier_dir/'initial-verifier.json',dict(return_code=before.return_code,stdout=before.stdout))
        assert before.return_code==0 and before.stdout.strip()==provenance['baseline'],before.stdout
        agent_cid=json.loads((trial/'agent-environment/handoff.json').read_text())['container_id']
        assert agent_cid!=env.cid
        patch=trial/'submission/submission.patch'
        if patch.stat().st_size:
            await env.upload_file(patch,'/tmp/submission.patch')
            applied=await env.exec('git apply --whitespace=nowarn /tmp/submission.patch')
            assert applied.return_code==0,applied.stdout
        program='import hashlib,json;from pathlib import Path;r=Path("/work");print(json.dumps({str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (r/"src").rglob("*.py")}))'
        observed=await env.exec('/usr/local/bin/python -I -c '+shlex.quote(program))
        assert observed.return_code==0 and json.loads(observed.stdout)==submission['source_sha256']
        clean=await env.exec('test ! -e /work/debug.tmp && test ! -e /work/probe-pid && test ! -e /tmp/codex-secrets && test ! -e /home/agent/.codex')
        assert clean.return_code==0
        await env.upload_file(ROOT/'private/hidden_tests.py','/tmp/hidden_tests.py')
        test=await env.exec('python /tmp/hidden_tests.py -v',timeout_sec=30)
        (self.trial_paths.verifier_dir/'hidden-tests.txt').write_text(test.stdout)
        assert test.return_code in (0,1)
        # The final line distinguishes test completion from a launch/import error.
        assert 'Ran 3 tests' in test.stdout
        passed=test.return_code==0
        save(self.trial_paths.verifier_dir/'result.json',dict(infrastructure_status='ok',passed=passed,
             hidden_test_exit_code=test.return_code,source_sha256=submission['source_sha256'],
             separate_containers=True,clean_base=True,only_source_transferred=True,
             agent_container=agent_cid,verifier_container=env.cid,
             known_solution_in_candidate=False,credential_in_verifier=False))
        save(self.trial_paths.verifier_dir/'reward.json',{'reward':float(passed)})
        return VerifierResult(rewards={'reward':float(passed)})


async def main(args):
    assert importlib.metadata.version('harbor')=='0.24.0'
    provenance=json.loads((args.task/'provenance.json').read_text())
    hashes=code_hashes();inputs=task_hashes(args.task)
    if args.live:
        assert provenance['live'] and args.auth_file and args.auth_file.is_file()
        assert args.approve_container_credentials and args.approve_public_network
        q=json.loads((args.qualification/'summary.json').read_text())
        assert q['passed'] and q['code_hashes']==hashes
        assert q['baseline']==provenance['baseline']
        assert q['runtime_bundle']==provenance['runtime_provenance']['codex_bundle_sha256']
        pre=json.loads((args.pytest_preflight/'summary.json').read_text())
        assert pre['passed'] and pre['tool_preflight_passed'] and pre['adapter_hashes']==adapter_hashes()
        controls=['codex']
    else:
        assert not provenance['live'];controls=['noop','complete','incomplete']
    args.output.mkdir(parents=True,exist_ok=False)
    canary=args.output/'fake-private-canary';canary.write_text('FAKE_PRIVATE_CANARY')
    summary=dict(passed=False,live=args.live,model=args.model if args.live else None,
        baseline=provenance['baseline'],code_hashes=hashes,task_hashes=inputs,
        runtime_bundle=provenance['runtime_provenance']['codex_bundle_sha256'],controls=[])
    save(args.output/'summary.json',summary)
    for name in controls:
        agent=AgentConfig(import_path='coding_preflight:ScriptedAgent',kwargs={'control':name})
        if args.live:
            agent=AgentConfig(import_path='codex_agent:PilotCodex',model_name=args.model,
                kwargs={'version':'0.162.1','config':pilot_config()},env={'CODEX_AUTH_JSON_PATH':str(args.auth_file)})
        cfg=TrialConfig(task=TaskConfig(path=args.task),trial_name=name,trials_dir=args.output,
            agent=agent,environment=EnvironmentConfig(import_path='environment:PilotEnvironment'),
            verifier=VerifierConfig(import_path='coding_preflight:SyntheticVerifier'))
        trial=await Trial.create(cfg)
        async def start(event):
            await public_gate(trial,provenance,[str(canary)])
        async def finish(event):
            await trial.agent_environment.freeze()
            if args.live and not getattr(trial.agent_environment,'agent_infrastructure_ok',False):
                raise RuntimeError('Unhealthy native Codex execution; no grading')
            if name=='complete':
                probe='from pathlib import Path;import time;p=Path("/proc")/Path("/work/probe-pid").read_text()/"status";assert not p.exists() or "Z" in p.read_text().split("State:")[1].splitlines()[0];s=Path("/work/src/service.py").stat().st_mtime_ns;time.sleep(.2);assert Path("/work/src/service.py").stat().st_mtime_ns==s;print("CHILD_STOPPED_SOURCE_FROZEN")'
                r=await trial.agent_environment.exec('/usr/local/bin/python -I -c '+shlex.quote(probe),user='root')
                assert r.return_code==0
                save(trial.paths.trial_dir/'process-check.json',dict(timeout_enforced=True,owned_child_stopped=True,source_stable=True,resource_exhaustion=False))
            collect_source(trial,args.task/'environment/base')
        trial.add_hook(TrialEvent.AGENT_START,start);trial.add_hook(TrialEvent.AGENT_END,finish)
        result=await trial.run()
        entry=dict(control=name,exception=result.exception_info.model_dump(mode='json') if result.exception_info else None)
        if not entry['exception']:
            graded=json.loads((trial.paths.verifier_dir/'result.json').read_text())
            entry.update(graded)
            entry['expectation_met']=args.live or graded['passed']==(name=='complete')
        else:entry['expectation_met']=False
        summary['controls'].append(entry);save(args.output/'summary.json',summary)
        print(json.dumps(entry),flush=True)
        if not entry['expectation_met']:raise RuntimeError('Preflight failed; no automatic trial retry')
    assert hashes==code_hashes() and inputs==task_hashes(args.task)
    summary['passed']=True;save(args.output/'summary.json',summary)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--live',action='store_true');p.add_argument('--model',default='openai/gpt-6.1-sol')
    p.add_argument('--auth-file',type=Path);p.add_argument('--qualification',type=Path);p.add_argument('--pytest-preflight',type=Path)
    p.add_argument('--approve-container-credentials',action='store_true');p.add_argument('--approve-public-network',action='store_true')
    a=p.parse_args()
    for key in ('task','output','auth_file','qualification','pytest_preflight'):
        if getattr(a,key) is not None:setattr(a,key,getattr(a,key).resolve())
    os.environ.update(DOCKER_HOST='unix:///private/tmp/pytest5786-colima/default/docker.sock',
        DOCKER_CONFIG=str(ROOT.parent/'tools/docker'),HOME=str(ROOT.parent/'tools/home'),PYTHONDONTWRITEBYTECODE='1')
    asyncio.run(main(a))
