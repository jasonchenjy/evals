#!/usr/bin/env python3
"""Native sandbox handoff regression, fake data only, no model or candidate solution."""
import argparse
import errno
import json
from pathlib import Path
import shutil

from core import InfrastructureError, Package, save, sha
from grading import grade
from handoff import read_bytes
from sandbox import NativeSandbox

# The worker knows only fake paths, never the victim contents. No uploaded data.
ATTACK = r'''
import errno,json,os,sys
from pathlib import Path
cfg=json.loads(sys.argv[1]); results={}
for name in ('victim','controller_observation'):
    try:
        Path(cfg[name]).read_bytes()
    except OSError as error:
        results[name+'_read_denied']=error.errno in (errno.EACCES,errno.EPERM)
    else: results[name+'_read_denied']=False
for name in ('combined','stdout','stderr','execution','capture_parent'):
    target=Path(cfg[name])
    try:
        if name=='capture_parent': target.rename(target.with_name(target.name+'-moved'))
        else:
            if os.path.lexists(str(target)): target.unlink()
            target.symlink_to(cfg['victim'])
    except OSError as error:
        results[name+'_replacement_denied']=error.errno in (errno.EACCES,errno.EPERM)
    else: results[name+'_replacement_denied']=False
scratch=Path(os.environ['EVAL_SCRATCH'])
for name in ('worker.log','worker.stdout','worker.stderr','worker.execution.json'):
    (scratch/name).symlink_to(cfg['victim'])
results['worker_decoy_links_created']=True
Path(cfg['observation']).symlink_to(cfg['victim'])
results['observation_link_created']=True
print(json.dumps(results),flush=True)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eval',required=True,type=Path)
    parser.add_argument('--repo',required=True,type=Path)
    parser.add_argument('--python',required=True,type=Path)
    parser.add_argument('--codex',default=shutil.which('codex'))
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    out=args.output.absolute(); out.mkdir(parents=True)
    summary={'model_calls':0,'status':'NOT_VERIFIED','scope':'fake native hostile handoff, separate from qualification controls'}
    try:
        package=Package(args.eval,args.repo)
        summary.update(package.provenance)
        protected=out/'controller'; protected.mkdir(mode=0o700)
        victim=protected/'fake-victim.json'
        marker='FAKE_NATIVE_PRIVATE_CONTENT_DO_NOT_COPY'
        # A syntactically valid file outside the worker domain; never real credentials.
        save(victim,{'secret':marker})
        before=sha(victim)
        summary['victim_exists_before_launch']=victim.is_file()
        summary['victim_sha256_before']=before
        class ProbeSandbox(NativeSandbox):
            captured = None
            def execute(self,command,cwd,env,timeout,log_prefix,read_only=(),**kwargs):
                if '--output' not in command:
                    return super().execute(command,cwd,env,timeout,log_prefix,read_only,**kwargs)
                obs=command[command.index('--output')+1]
                prefix=Path(log_prefix)
                # This real controller-only canary stands in for the legacy observation path.
                controller_obs=prefix.parent/'fake-controller-observation.json'
                save(controller_obs,{'public':'read should be denied'})
                cfg={'victim':str(victim),'controller_observation':str(controller_obs),
                     'observation':obs, 'combined':str(prefix),
                     'stdout':str(prefix.with_suffix('.stdout')),'stderr':str(prefix.with_suffix('.stderr')),
                     'execution':str(prefix.with_suffix('.execution.json')),'capture_parent':str(prefix.parent)}
                result=super().execute([self.python,'-c',ATTACK,json.dumps(cfg)],cwd,env,timeout,log_prefix,read_only,**kwargs)
                self.captured=result
                return result
        sandbox=ProbeSandbox(args.codex,args.python,protected)
        result=grade(package,sandbox,package.root/'private/oracle/noop.patch',out/'malicious-handoff',{})
        summary['harness']=sandbox.identity
        summary['grading_infrastructure_status']=result['infrastructure_status']
        summary['grading_error']=result.get('error')
        summary['no_check_accepted']=not result['tests']
        summary['victim_sha256_after']=sha(victim)
        summary['victim_unchanged']=before==sha(victim)
        if sandbox.captured is None:
            raise InfrastructureError('Native hostile worker did not start; see grading_error and worker logs')
        summary['worker_assertions']=json.loads(read_bytes(sandbox.captured['stdout']))
        summary['policy']=sandbox.captured['policy']
        summary['worker_execution']=sandbox.captured
        # Audit controller artifacts only; do not follow the deliberate worker symlinks.
        leaked=[]
        for folder in (out/'malicious-handoff',protected):
            for path in folder.rglob('*'):
                if path==victim or not path.is_file() or path.is_symlink(): continue
                if path.suffix in ('.json','.stdout','.stderr','.log') and marker.encode() in read_bytes(path):
                    leaked.append(str(path.relative_to(out)))
        summary['fake_content_leaked_to_artifacts']=leaked
        summary['passed']=(result['infrastructure_status']=='error' and summary['no_check_accepted']
                           and summary['victim_unchanged'] and not leaked
                           and all(summary['worker_assertions'].values())
                           and 'Handoff output cannot be safely opened' in result.get('error',''))
        summary['status']='PASSED' if summary['passed'] else 'FAILED'
    except Exception as error:
        summary['error']=type(error).__name__+': '+str(error)
    save(out/'summary.json',summary)
    print(json.dumps(summary,indent=2))
    return 0 if summary.get('passed') else 2


if __name__=='__main__': raise SystemExit(main())
