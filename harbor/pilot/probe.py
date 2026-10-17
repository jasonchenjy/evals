"""Harmless real-container probes; no model calls or credential reads."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import sys

from common import ROOT, REPO, load_runtime, save
sys.path.insert(0, str(ROOT))
from environment import PilotEnvironment
from harbor.models.task.config import EnvironmentConfig as TaskEnvironment
from harbor.models.trial.paths import TrialPaths
from harbor.models.task.config import NetworkPolicy


async def agent_probes(task, output):
    results = []
    for case in ['background', 'nondumpable-background', 'outside-hardlink', 'symlink', 'fifo', 'oversize', 'output-cap', 'timeout', 'pid-limit']:
        paths = TrialPaths(trial_dir=output/case)
        paths.trial_dir.mkdir(parents=True)
        env = PilotEnvironment(environment_dir=task/'environment', environment_name='pilot-probe',
            session_id=case, trial_paths=paths,
            task_env_config=TaskEnvironment(cpus=2, memory_mb=4096, network_mode='no-network'),
            network_policy=NetworkPolicy(network_mode='no-network'))
        try:
            await env.start(False)
            if case in ('background', 'nondumpable-background'):
                child = "import time;from pathlib import Path\nwhile True:\n Path('/work/src/pilot_helper.py').write_text('X=1\\n');time.sleep(.01)"
                if case == 'nondumpable-background':
                    child = 'import ctypes;assert ctypes.CDLL(None).prctl(4,0)==0\n' + child
                program = 'import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,"-c",'+repr(child)+'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);Path("/work/probe-pid").write_text(str(p.pid));time.sleep(.1)'
            elif case == 'outside-hardlink':
                program = "from pathlib import Path;import os;Path('/work/outside.py').write_text('x=1');os.link('/work/outside.py','/work/src/pilot_helper.py')"
            elif case == 'symlink':
                program = "from pathlib import Path;Path('/work/src/pilot_helper.py').symlink_to('/fake-private')"
            elif case == 'fifo':
                program = "import os;os.mkfifo('/work/src/pilot_helper.py')"
            elif case == 'oversize':
                program = "from pathlib import Path;Path('/work/src/pilot_helper.py').write_bytes(b'x'*(2*1024*1024+1))"
            elif case == 'output-cap':
                program = "import sys;sys.stdout.write('x'*(17*1024*1024))"
            elif case == 'timeout':
                program = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(600)'],start_new_session=True);time.sleep(600)"
            else:
                program = '''import subprocess,errno,json
children=[];hit=False
try:
 for i in range(140):
  try: children.append(subprocess.Popen(['sleep','60']))
  except OSError as e: hit=e.errno==errno.EAGAIN;break
finally:
 for p in children:p.kill()
 for p in children:p.wait()
print(json.dumps({'pid_limit_enforced':hit,'children':len(children)}));assert hit
'''
            rejected = False
            try:
                result = await env.exec('/usr/local/bin/python -I -c '+shlex.quote(program),
                                        user='1000:1000', timeout_sec=1 if case=='timeout' else 20)
                assert result.return_code == 0, str(result)
                save(paths.trial_dir/'probe-execution.json', dict(return_code=result.return_code,stdout=result.stdout))
            except (RuntimeError, TimeoutError) as error:
                if case not in ('output-cap','timeout'): raise
                rejected = True
                save(paths.trial_dir/'expected-rejection.json', dict(reason=type(error).__name__))
            unsafe = case in ('outside-hardlink','symlink','fifo','oversize')
            try:
                await env.freeze()
            except RuntimeError:
                if not unsafe: raise
                rejected = True
            assert rejected == (unsafe or case in ('output-cap','timeout'))
            if case in ('background','nondumpable-background'):
                check = 'from pathlib import Path;p=Path("/proc")/Path("/work/probe-pid").read_text()/"status";assert not p.exists() or "Z" in p.read_text().split("State:")[1].splitlines()[0]'
                stopped=await env.exec('/usr/local/bin/python -I -c '+shlex.quote(check),user='root')
                assert stopped.return_code==0
            results.append(dict(case=case, passed=True, rejected=rejected))
        finally:
            await env.stop(True)
        save(output/'agent-probes.json', results)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--task',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',required=True)
    p.add_argument('--endpoint',default='unix:///private/tmp/pytest5786-colima/default/docker.sock')
    a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
    os.environ.update(DOCKER_HOST=a.endpoint,DOCKER_CONFIG=str(ROOT/'tools/docker'),HOME=str(ROOT/'tools/home'),PYTHONDONTWRITEBYTECODE='1')
    asyncio.run(agent_probes(a.task.resolve(),a.output))
    load_runtime()
    from container_boundary import DockerBoundary,resource_probe
    boundary=DockerBoundary('/usr/local/bin/docker',a.endpoint,ROOT/'tools/docker',a.image,a.output/'worker-resources')
    resource_probe(boundary)
    save(a.output/'summary.json',dict(agent_cases=9,worker_resource_probes='PASSED',model_calls=0,passed=True))


if __name__=='__main__':main()
