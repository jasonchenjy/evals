"""Deterministic local Responses fixture; no real inference and no Eval solving."""
import argparse,json,subprocess,uuid
from pathlib import Path
from runtime_inventory import DOCKER

CONTAINER = r'''
import json,os,pathlib,subprocess,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
bundle=pathlib.Path('/opt/codex/bin/codex').is_file()
cli='/opt/codex/bin/codex' if bundle else '/usr/local/bin/codex'
source='/seed/workspace/src' if bundle else '/base/src'
os.environ.update(PATH=('/opt/codex/bin:/opt/codex/codex-path:' if bundle else '')+'/opt/pytest-python/bin:/usr/local/bin:/usr/bin:/bin',
 PYTHONPATH=source,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONDONTWRITEBYTECODE='1')
pathlib.Path(os.environ['CODEX_HOME']).mkdir(parents=True,exist_ok=True)
commands=[
 'text(await tools.exec_command('+json.dumps({'cmd':"printf 'VALUE = 1\\n' > probe.py; printf 'from probe import VALUE\\ndef test_value():\\n    assert VALUE == 2\\n' > test_probe.py; git init -q; git add probe.py test_probe.py; git -c user.name=Audit -c user.email=audit@invalid commit -qm baseline; command -v python; command -v rg; command -v apply_patch; command -v applypatch",'login':False,'max_output_tokens':1500})+'));',
 'text(await tools.apply_patch('+json.dumps('*** Begin Patch\n*** Update File: /work/probe.py\n@@\n-VALUE = 1\n+VALUE = 2\n*** End Patch')+'));',
 'text(await tools.exec_command('+json.dumps({'cmd':"command -v python; command -v rg; python -m pytest -q test_probe.py; git diff -- probe.py",'max_output_tokens':2000})+'));',
 'text(await tools.exec_command('+json.dumps({'cmd':"command -v python; command -v rg; /opt/pytest-python/bin/python -m pytest -q test_probe.py; git diff -- probe.py",'login':False,'max_output_tokens':2000})+'));'
]
commands += [
 'const r = await tools.exec_command('+json.dumps({'cmd':"/usr/local/bin/python -u -c 'import time;print(\"SESSION_START\");time.sleep(2);print(\"SESSION_DONE\")'",'login':False,'tty':True,'yield_time_ms':1000,'max_output_tokens':500})+'); text(r); if (r.session_id) text(await tools.write_stdin({session_id:r.session_id,chars:"",yield_time_ms:1000,max_output_tokens:500}));',
 'text(await tools.exec_command({cmd:"exit 7",login:false,max_output_tokens:100}));'
]
requests=[]
class Fixture(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  n=int(self.headers.get('Content-Length','0'))
  if n<=0 or n>2*1024*1024:self.send_error(413);return
  body=json.loads(self.rfile.read(n));requests.append(body);index=len(requests)-1
  rid='resp_audit_'+str(index)
  events=[{'type':'response.created','response':{'id':rid,'object':'response','model':'offline-fixture','status':'in_progress','output':[]}}]
  if index<len(commands):
   item={'id':'ctc_audit_'+str(index),'type':'custom_tool_call','status':'completed','call_id':'call_audit_'+str(index),'name':'exec','input':commands[index]}
  else:item={'id':'msg_audit','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'Deterministic offline fixture finished; this is not a model response.','annotations':[]}]}
  events.append({'type':'response.output_item.done','output_index':0,'item':item})
  events.append({'type':'response.completed','response':{'id':rid,'object':'response','model':'offline-fixture','status':'completed','output':[item],'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0}}})
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
  for seq,event in enumerate(events):
   event['sequence_number']=seq
   self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()
server=HTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=server.serve_forever,daemon=True).start()
args=[cli,'--no-daemon','--enable','unified_exec','--disable','enable_request_compression','-c','model_provider="offline_audit"',
 '-c','model_providers.offline_audit.name="Deterministic fixture"',
 '-c','model_providers.offline_audit.base_url="http://127.0.0.1:'+str(server.server_port)+'"',
 '-c','model_providers.offline_audit.wire_api="responses"','-c','model_providers.offline_audit.requires_openai_auth=false',
 '-c','model_providers.offline_audit.request_max_retries=0','-c','model_providers.offline_audit.stream_max_retries=0',
 '-c','web_search="disabled"','exec','--dangerously-bypass-approvals-and-sandbox','--skip-git-repo-check','--json','--model','gpt-6.1-sol',
 'Offline transport audit only. The localhost fixture supplies all outputs. Work only on probe.py and test_probe.py. No benchmark task.']
try:
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=85)
 result={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
except subprocess.TimeoutExpired as e:result={'timeout':True,'stdout':str(e.stdout),'stderr':str(e.stderr)}
finally:server.shutdown();server.server_close()
outputs=[]
for req in requests:
 for item in req.get('input',[]):
  if item.get('type') in ['custom_tool_call_output','function_call_output'] and item not in outputs:outputs.append(item)
result.update(real_model_calls=0,local_fixture_requests=len(requests),tools=(requests[0].get('tools',[])+[t for x in requests[0].get('input',[]) if x.get('type')=='additional_tools' for t in x.get('tools',[])]) if requests else [],
 request_shape={'keys':list(requests[0]),'input_types':[x.get('type') for x in requests[0].get('input',[])]} if requests else {},
 tool_outputs=outputs,code_home=os.environ['CODEX_HOME'],
 toy_files={name:pathlib.Path('/work',name).read_text() for name in ['probe.py','test_probe.py'] if pathlib.Path('/work',name).is_file()})
print(json.dumps(result,indent=2))
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--temporary-home',action='store_true');a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False)
 name='harbor-offline-tools-'+uuid.uuid4().hex[:12]
 argv=[*DOCKER,'create','--name',name,'--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--cpus','2','--memory','4g','--memory-swap','4g','--log-driver','none','--ulimit','fsize=33554432:33554432']
 for value in ['/work:rw,nosuid,nodev,size=1536m,mode=755,uid=1000,gid=1000','/home/agent:rw,nosuid,nodev,size=64m,mode=755,uid=1000,gid=1000','/tmp:rw,nosuid,nodev,size=256m,mode=1777','/logs:rw,nosuid,nodev,size=128m,mode=777']:argv+=['--tmpfs',value]
 argv+=['--env','HOME=/home/agent','--env','CODEX_HOME='+('/tmp/codex-home' if a.temporary_home else '/home/agent/.codex'),'--workdir','/work','--entrypoint','/usr/local/bin/python',a.image,'-I','-c',CONTAINER]
 cid=subprocess.check_output(argv,text=True).strip()
 try:
  info=json.loads(subprocess.check_output([*DOCKER,'inspect',cid]))[0]
  assert info['HostConfig']['NetworkMode']=='none' and not info['Mounts']
  (a.output/'container.json').write_text(json.dumps({k:info[k] for k in ['Id','Image','HostConfig','Mounts']},indent=2)+'\n')
  r=subprocess.run([*DOCKER,'start','-a',cid],capture_output=True,text=True,timeout=100)
  (a.output/'result.json').write_text(r.stdout);(a.output/'stderr.txt').write_text(r.stderr)
  assert r.returncode==0,r.stderr[-1000:]
  data=json.loads(r.stdout);print({k:data.get(k) for k in ['returncode','timeout','real_model_calls','local_fixture_requests','toy_files']})
 finally:
  subprocess.run([*DOCKER,'rm','-f',cid],check=True,capture_output=True)
  removed=subprocess.run([*DOCKER,'inspect',cid],capture_output=True).returncode!=0
  (a.output/'audit.json').write_text(json.dumps(dict(real_auth_used=False,real_model_calls=0,network='none',benchmark_executed=False,removed=removed),indent=2)+'\n')

if __name__=='__main__':main()
