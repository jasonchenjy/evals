"""Offline inventory of existing images; no model, auth, or benchmark execution."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///private/tmp/pytest5786-colima/default/docker.sock',
          '--config', str(Path('harbor/tools/docker').resolve())]
SCRIPT = r'''
import json,os,pathlib,shutil,subprocess,sys,stat,resource
root=pathlib.Path('/work');home=pathlib.Path('/home/agent/.codex');home.mkdir(parents=True)
records=[]
commands=[
 ['uname','-m'],['bash','--version'],['git','--version'],['python','--version'],
 ['python','-c','import sys,ssl;print(sys.executable);print(ssl.OPENSSL_VERSION)'],
 ['python','-c','import importlib.metadata as m;print({x:m.version(x) for x in ["pytest","pytest-xdist","execnet","attrs","pluggy"]})'],
 ['bash','-lc','printf "PATH=%s\\n" "$PATH"; command -v codex; command -v rg; command -v python'],
 ['bash','-c','printf "PATH=%s\\n" "$PATH"; command -v codex; command -v rg; command -v python'],
]
for name in ['codex','codex-code-mode-host','rg','bwrap','zsh']:
 for base in ['/usr/local/bin','/usr/bin','/opt/codex/bin','/opt/codex/codex-path','/opt/codex/codex-resources','/opt/codex/codex-resources/zsh/bin']:
  p=pathlib.Path(base,name)
  if p.is_file():
   commands.append([str(p),'--help'] if name in ['codex-code-mode-host','bwrap'] else [str(p),'--version'])
   if name=='codex':commands.extend([[str(p),'debug','--help'],[str(p),'features','list'],[str(p),'app-server','--help']])
   if name in ['rg','zsh','bwrap']:commands.append(['ldd',str(p)])
for argv in commands:
 try:
  p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=12)
  records.append(dict(argv=argv,returncode=p.returncode,stdout=p.stdout[:65536],stderr=p.stderr[:16384]))
 except (OSError,subprocess.TimeoutExpired) as e:records.append(dict(argv=argv,error=str(e)))
paths={n:shutil.which(n) for n in ['bash','sh','zsh','git','rg','python','python3','node','npm','tee','tar','patch','apply_patch','applypatch','curl','cat','sed','find','xargs','timeout','base64','ps']}
print(json.dumps(dict(uid=os.getuid(),path=os.environ['PATH'],commands_on_path=paths,
 dirs={p:dict(exists=pathlib.Path(p).exists(),writable=os.access(p,os.W_OK)) for p in ['/work','/tmp','/logs','/home/agent','/usr/local/bin','/opt/codex']},
 fsize_limit=resource.getrlimit(resource.RLIMIT_FSIZE),commands=records),indent=2))
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False)
 name='harbor-offline-audit-'+uuid.uuid4().hex[:12]
 create=[*DOCKER,'create','--name',name,'--network','none','--read-only','--user','1000:1000',
 '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--cpus','2',
 '--memory','4g','--memory-swap','4g','--log-driver','none','--ulimit','fsize=33554432:33554432',
 '--tmpfs','/work:rw,nosuid,nodev,size=1536m,mode=755,uid=1000,gid=1000',
 '--tmpfs','/home/agent:rw,nosuid,nodev,size=64m,mode=755,uid=1000,gid=1000',
 '--tmpfs','/tmp:rw,nosuid,nodev,size=256m,mode=1777','--tmpfs','/logs:rw,nosuid,nodev,size=128m,mode=777',
 '--env','HOME=/home/agent','--env','CODEX_HOME=/home/agent/.codex','--env','PYTHONPATH=',
 '--workdir','/work','--entrypoint','/usr/local/bin/python',a.image,'-I','-c',SCRIPT]
 cid=subprocess.check_output(create,text=True).strip()
 try:
  info=json.loads(subprocess.check_output([*DOCKER,'inspect',cid]))[0]
  assert not info['Mounts'] and info['HostConfig']['NetworkMode']=='none' and info['HostConfig']['ReadonlyRootfs']
  (a.output/'container.json').write_text(json.dumps({k:info[k] for k in ['Id','Image','HostConfig','Mounts']},indent=2)+'\n')
  result=subprocess.run([*DOCKER,'start','-a',cid],capture_output=True,text=True,timeout=150)
  (a.output/'stdout.json').write_text(result.stdout)
  (a.output/'stderr.txt').write_text(result.stderr)
  assert result.returncode==0,result.stderr[-1000:]
  parsed=json.loads(result.stdout)
  print(json.dumps({'image':a.image,'uid':parsed['uid'],'path':parsed['path'],'commands_on_path':parsed['commands_on_path'],'checks':len(parsed['commands'])}))
 finally:
  subprocess.run([*DOCKER,'rm','-f',cid],capture_output=True,check=True)
  removed=subprocess.run([*DOCKER,'inspect',cid],capture_output=True).returncode!=0
  (a.output/'audit.json').write_text(json.dumps(dict(image=a.image,network='none',real_auth_used=False,model_calls=0,benchmark_executed=False,removed=removed),indent=2)+'\n')
  assert removed

if __name__=='__main__':main()
