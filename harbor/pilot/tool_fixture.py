"""Local deterministic Responses fixture for native Codex tools, never inference.

Used only by live_preflight.py. It listens on loopback, has no upstream, receives
fake authentication only, and edits an unrelated disposable source file.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def shell(cmd, **kwargs):
    return 'text(await tools.exec_command(' + json.dumps(dict(cmd=cmd, max_output_tokens=3000, **kwargs)) + '));'


CHECK_ENV = '''import sys,pkg_resources,pytest,json
assert sys.executable == '/opt/pytest-python/bin/python', sys.executable
assert sys.version_info[:3] == (3,8,20)
assert pytest.__file__ == '/work/src/pytest.py'
reqs=[pkg_resources.Requirement.parse(x) for x in open('/work/eval_requirements.txt')]
assert all(pkg_resources.get_distribution(r.project_name) in r for r in reqs)
assert pkg_resources.get_distribution('pytest-xdist').version == '1.29.0'
print('PINNED_ENV_OK',sys.executable,pytest.__file__)
'''
PUBLIC_TESTS = '''import subprocess,sys
for opts in [[],['-p','xdist.plugin','-n','2']]:
 p=subprocess.run([sys.executable,'-m','pytest','-q','eval_public/test_example.py']+opts,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 print(p.stdout)
 assert p.returncode == 1 and '2 failed' in p.stdout
print('PUBLIC_AND_XDIST_OK: two intentional failures in each mode')
'''
import shlex
commands = [
    shell("set -e; test -w /work/src; git rev-list --count HEAD; rg -n 'def test_' eval_public/test_example.py; command -v rg; command -v apply_patch; python -c " + shlex.quote(CHECK_ENV), login=False),
    'text(await tools.apply_patch(' + json.dumps('*** Begin Patch\n*** Add File: /work/src/harbor_tool_probe.py\n+VALUE = 2\n*** Add File: /tmp/test_harbor_tool_probe.py\n+from harbor_tool_probe import VALUE\n+def test_value():\n+    assert VALUE == 2\n*** End Patch') + '));',
    shell('set -e; python -c ' + shlex.quote(CHECK_ENV) + '; python -m pytest -q /tmp/test_harbor_tool_probe.py'),
    shell('set -e; python -c ' + shlex.quote(CHECK_ENV) + '; python -m pytest -q /tmp/test_harbor_tool_probe.py', login=False),
    shell('python -c ' + shlex.quote(PUBLIC_TESTS)),
    'const r=await tools.exec_command({cmd:"sleep 2; echo PTY_DONE",tty:true,login:false,yield_time_ms:1000,max_output_tokens:100});text(r);if(r.session_id)text(await tools.write_stdin({session_id:r.session_id,chars:"",yield_time_ms:1000,max_output_tokens:100}));',
    shell('exit 7', login=False),
]
requests = []


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= 2*1024*1024 or len(requests) > len(commands):
            self.send_error(413)
            return
        request = json.loads(self.rfile.read(size))
        requests.append(request)
        index = len(requests)-1
        outputs = [x for r in requests for x in r.get('input', []) if x.get('type') == 'custom_tool_call_output']
        Path('/logs/agent/offline-fixture.json').write_text(json.dumps(dict(requests=len(requests),real_model_calls=0,outputs=outputs),indent=2))
        rid = 'resp_fixture_' + str(index)
        if index < len(commands):
            item = dict(id='ctc_'+str(index),type='custom_tool_call',status='completed',call_id='call_'+str(index),name='exec',input=commands[index])
        else:
            item = dict(id='msg_fixture',type='message',role='assistant',status='completed',content=[dict(type='output_text',text='Offline fixture complete; no real inference.',annotations=[])])
        events = [dict(type='response.created',response=dict(id=rid,object='response',model='offline-fixture',status='in_progress',output=[])),
                  dict(type='response.output_item.done',output_index=0,item=item),
                  dict(type='response.completed',response=dict(id=rid,object='response',model='offline-fixture',status='completed',output=[item],usage=dict(input_tokens=0,output_tokens=0,total_tokens=0)))]
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Connection','close')
        self.end_headers()
        for seq,event in enumerate(events):
            event['sequence_number']=seq
            self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode())
            self.wfile.flush()


if __name__ == '__main__':
    server=HTTPServer(('127.0.0.1',8765),Fixture)
    Path('/tmp/fixture-ready').write_text('ready')
    server.serve_forever()
