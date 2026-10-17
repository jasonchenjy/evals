"""Supplemental no-model content-search and stream observation in Harbor."""
import argparse,asyncio,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pilot'));sys.path.insert(1,str(ROOT))
from environment import PilotEnvironment
from common import save
from harbor.models.task.config import EnvironmentConfig,NetworkPolicy
from harbor.models.trial.paths import TrialPaths

async def main(args):
    args.output.mkdir(parents=True,exist_ok=False)
    env=PilotEnvironment(environment_dir=args.task/'environment',environment_name='coding-search',session_id='search',
        trial_paths=TrialPaths(trial_dir=args.output),task_env_config=EnvironmentConfig(cpus=2,memory_mb=4096,network_mode='no-network'),
        network_policy=NetworkPolicy(network_mode='no-network'))
    try:
        await env.start(False)
        command="rg -n '^(def |from )|parse_order|validate_order' src"
        result=await env.exec(command,user='1000:1000')
        assert result.return_code==0 and all(n in result.stdout for n in ['src/parser.py','src/validator.py','src/service.py'])
        streams=await env.exec("python -c 'import sys;print(\"STDOUT_MARKER\");print(\"STDERR_MARKER\",file=sys.stderr);sys.exit(7)'",user='1000:1000')
        assert streams.return_code==7 and all(x in streams.stdout for x in ['STDOUT_MARKER','STDERR_MARKER'])
        save(args.output/'summary.json',dict(passed=True,real_model_calls=0,genuine_agent_behavior=False,
            content_search_command=command,content_search_output=result.stdout,
            exit_code=streams.return_code,merged_stdout_stderr=streams.stdout))
    finally:await env.stop(True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.task=a.task.resolve();a.output=a.output.resolve()
    os.environ.update(DOCKER_HOST='unix:///private/tmp/pytest5786-colima/default/docker.sock',
        DOCKER_CONFIG=str(ROOT/'tools/docker'),HOME=str(ROOT/'tools/home'),PYTHONDONTWRITEBYTECODE='1')
    asyncio.run(main(a))
