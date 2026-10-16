"""Capture an actual CLI Responses request against a rejecting local fixture.

No request is forwarded to a model; no tool calls are returned or executed.
This is inventory evidence only, never authorization to open the live gate.
"""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
import re

from core import Package, bounded, save, sha
from agent import client_env, prompt

DISABLE = ['apps','plugins','remote_plugin','browser_use','browser_use_external','browser_use_full_cdp_access',
           'computer_use','memories','hooks','multi_agent','multi_agent_v2','shell_snapshot','workspace_dependencies',
           'code_mode','code_mode_host','code_mode_only','image_generation','view_image','goals',
           'skill_search','skill_mcp_dependency_install','in_app_browser','in_app_local_automation',
           'worktrees','enable_request_compression','unbounded_connection_retries','sleep_tool']


def request_inventory(payload):
    definitions = list(payload.get('tools', []))
    for item in payload.get('input', []):
        if item.get('type') == 'additional_tools':
            definitions.extend(item.get('tools', []))
    direct, nested = [], []
    def visit(items, prefix=''):
        for item in items:
            name = prefix + item.get('name', item.get('type', 'unknown'))
            if item.get('type') == 'namespace':
                visit(item.get('tools', []), name+'.')
            else:
                direct.append(name)
                nested.extend(re.findall(r'^### `([^`]+)`', item.get('description',''), re.M))
    visit(definitions)
    prohibited = [x for x in direct if x.startswith('collaboration.')]
    prohibited += [x for x in nested if 'mcp_resource' in x]
    return {'direct_tools':direct, 'documented_nested_tools':nested,
            'prohibited_or_unnecessary_tools':prohibited,
            'complete_dynamic_inventory_verified':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--codex',required=True);p.add_argument('--eval',required=True,type=Path)
    p.add_argument('--repo',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();out=a.output.absolute();out.mkdir(parents=True)
    package=Package(a.eval,a.repo);work=out/'workspace';package.prepare(work)
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>2*1024*1024:
                self.send_error(413);return
            # No request headers are retained; authentication is neither needed nor read.
            body=json.loads(self.rfile.read(n))
            requests.append(body)
            self.send_response(400);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(b'{"error":{"message":"Deterministic inventory fixture; no inference performed","type":"invalid_request_error"}}')
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    env=client_env(out/'fresh-client')
    command=[a.codex,'--no-daemon','-a','never']
    for feature in DISABLE:command += ['--disable',feature]
    command += ['--enable','skip_host_skill_discovery']
    settings={'model_provider':'inventory_fixture','web_search':'disabled','project_doc_max_bytes':0,
              'developer_instructions':'','mcp_servers':{},'cli_auth_credentials_store':'file',
              'model_providers.inventory_fixture':{'name':'Inventory fixture, no model',
                'base_url':'http://127.0.0.1:'+str(server.server_port),'wire_api':'responses',
                'requires_openai_auth':False,'request_max_retries':0,'stream_max_retries':0}}
    # TOML inline tables use =, unlike JSON. Leaf overrides avoid ambiguous parsing.
    for key,value in settings.items():
        if isinstance(value,dict):
            if not value: command += ['-c',key+'={}']
            else:
                for sub,item in value.items():command += ['-c',key+'.'+sub+'='+json.dumps(item)]
        else:command += ['-c',key+'='+json.dumps(value)]
    system=Path(env['CODEX_HOME'])/'skills/.system'
    command += ['-c','skills.config=['+', '.join('{path='+json.dumps(str(system/name/'SKILL.md'))+',enabled=false}' for name in ('imagegen','openai-docs','skill-creator','skill-installer'))+']']
    command += ['exec','--ignore-user-config','--ignore-rules','--ephemeral','--json','--sandbox','read-only',
                '-C',str(work),'--model','gpt-6.1-sol','-']
    try:
        execution=bounded(command,work,env,25,out/'cli',prompt(work,'/opt/pytest-python/bin/python'))
    finally:
        server.shutdown();server.server_close();thread.join(2)
    for i,body in enumerate(requests):save(out/('request-%d.json'%i),body)
    save(out/'result.json',{'status':'PASSED' if requests else 'NOT_VERIFIED','model_calls':0,
       'fixture_requests':len(requests),'requested_model':'gpt-6.1-sol','cli_sha256':sha(a.codex),
       'execution':execution,'inventory':request_inventory(requests[0]) if requests else None,
       'effective_tools_verified':False,'live_gate_open':False,
       'limitation':'Real request serialization observed against a rejecting offline fixture. Remote tool routing, live provider request equivalence, and dedicated authentication remain unverified.'})
    print('fixture requests:',len(requests),'real model calls: 0; live gate remains closed')


if __name__=='__main__':main()
