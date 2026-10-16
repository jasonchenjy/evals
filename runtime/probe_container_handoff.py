"""Real container adversarial file handoff regression using only fake host files."""
import argparse
import json
from pathlib import Path
from core import Package, clean_env, save, InfrastructureError
from container_sandbox import ContainerSandbox
from handoff import read_bytes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eval',required=True,type=Path);p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--image',required=True);p.add_argument('--endpoint',required=True)
    p.add_argument('--client-config',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();out=a.output.absolute();out.mkdir(parents=True)
    package=Package(a.eval,a.repo);work=out/'workspace';baseline=package.prepare(work)
    sandbox=ContainerSandbox('/usr/local/bin/docker',a.endpoint,a.client_config,a.image,out/'controller')
    staged=out/'immutable-inputs';staged.mkdir();(staged/'boundary_canary.txt').write_text('immutable fake test input')
    sandbox.canaries(work,out/'filesystem',read_only=[staged],readonly_canary=staged/'boundary_canary.txt')
    canary=out/'controller-fake-private';secret='FAKE_PRIVATE_VALUE_DO_NOT_COPY_5786';canary.write_text(secret)
    save(out/'canary-exists.json',{'exists_before_execution':canary.is_file(),'path':str(canary)})
    rows=[]
    valid={'schema_version':1,'method':'probe','tests_run':1,'status':'passed','duration_seconds':0,
           'failures':[],'skips':[],'details':[]}
    for name in ('normal','log-link','stdout-link','stderr-link','record-link','observation-link','observation-fifo','observation-large','observation-json','parent-link'):
        folder=out/name;folder.mkdir()
        env=clean_env(work,folder/'scratch',sandbox.python)
        program='''import json,os,pathlib,sys
canary=sys.argv[1];kind=sys.argv[2];target=pathlib.Path(os.environ['EVAL_SCRATCH'])/'observation.json'
try: open(canary,'rb').read(1)
except OSError: pass
else: raise AssertionError('Host fake file unexpectedly readable')
try: open(canary,'w').write('bad')
except OSError: pass
else: raise AssertionError('Host fake file unexpectedly writable')
if kind=='observation-link': target.symlink_to(canary)
elif kind=='observation-fifo': os.mkfifo(str(target))
elif kind=='observation-large': target.write_bytes(b'x'*(1024*1024+1))
elif kind=='observation-json': target.write_text('invalid json')
elif kind=='parent-link':
 scratch=target.parent;os.rename(str(scratch),str(scratch)+'-old');scratch.symlink_to(pathlib.Path(canary).parent)
else:
 target.write_text(sys.argv[3])
 paths={'log-link':'/trial/scratch/worker.log','stdout-link':'/trial/capture/process.stdout','stderr-link':'/trial/capture/process.stderr','record-link':'/trial/capture/process.execution.json'}
 if kind in paths:
  dest=pathlib.Path(paths[kind])
  if dest.exists(): dest.unlink()
  dest.symlink_to(canary)
 print('normal public log')
'''
        accepted=name in ('normal','log-link')
        try:
            execution=sandbox.execute([sandbox.python,'-c',program,str(canary),name,json.dumps(valid),'--method','probe','--output',str(folder/'scratch/observation.json')],
                                      work,env,8,folder/'worker')
            rejected=False
            if execution['returncode'] != 0: raise AssertionError('Probe did not execute normally')
            if not accepted: raise AssertionError('Unsafe handoff accepted: '+name)
            if json.loads((folder/'scratch/observation.json').read_text()) != valid:raise AssertionError('Normal observation changed')
            if b'normal public log' not in read_bytes(execution['stdout']):raise AssertionError('Normal logs missing')
        except InfrastructureError as error:
            rejected=True
            if accepted:raise
            save(folder/'rejection.json',{'reason':str(error),'category':'infrastructure_failure'})
        if canary.read_text()!=secret:raise AssertionError('Controller fake file changed')
        # Inspect only our own transport captures/result logs, never credentials.
        for root in (folder,out/'controller'):
            for f in root.rglob('*'):
                if f.is_file() and f.suffix in ('.stdout','.stderr','.json') and '/images/' not in str(f):
                    if secret.encode() in f.read_bytes():raise AssertionError('Private fake content leaked')
        rows.append({'case':name,'expected_rejection':not accepted,'rejected':rejected,'canary_unchanged':True,'no_private_content':True})
        save(out/'results.json',{'status':'RUNNING','cases':rows,'model_calls':0})
    save(out/'results.json',{'status':'PASSED','cases':rows,'model_calls':0,'baseline':baseline,
                            'scope':'container boundary, no native policy bypass, no real credentials'})
    print('PASSED',len(rows),'real container handoff cases')


if __name__=='__main__':main()
