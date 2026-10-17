"""One bounded synthetic live account check; never runs a benchmark or retries.

Real authentication is read by this trusted host controller only AFTER isolation
preflight. Only access token/account ID cross stdin to a trusted broker process.
Candidate receives an opaque expiring nonce; no auth mounts or real account data.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
HARBOR = HERE.parents[1]
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///private/tmp/pytest5786-colima/default/docker.sock', '--config', str(HARBOR / 'tools/docker')]
BASE = 'harbor-pilot-base:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12'
PROMPT = ('This is a synthetic transport validation, not a benchmark. Work only in /work. '
          'Read arithmetic.py and test_arithmetic.py. Fix add(a,b) to return the sum, '
          'run python -m pytest -q test_arithmetic.py, and report the result. '
          'Do not inspect or modify authentication or network configuration.')


def docker(*args, check=True, input_text=None, timeout=30):
    r = subprocess.run([*DOCKER, *args], input=input_text, text=True, capture_output=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError('docker_' + args[0] + '_failed')  # no secret-bearing errors
    return r


def upload(container, target, content):
    docker('exec', '-i', container, '/usr/local/bin/python', '-I', '-c',
           'import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())', target, input_text=content)


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def scan(container, sensitive):
    # All writable trees and process environment are streamed to the trusted host.
    # The real secrets are NOT passed to the scanning process in the candidate.
    script = '''import tarfile,sys,pathlib
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as t:
 for root in ['/work','/tmp','/logs','/home/agent']:
  t.add(root, recursive=True)
 for p in pathlib.Path('/proc').glob('[0-9]*/environ'):
  try:
   import io
   b=p.read_bytes();info=tarfile.TarInfo(str(p));info.size=len(b);t.addfile(info,io.BytesIO(b))
  except (OSError,PermissionError):pass
'''
    proc = subprocess.Popen([*DOCKER, 'exec', container, '/usr/local/bin/python', '-I', '-c', script], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    hashes = {}
    try:
        with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
            for entry in archive:
                if entry.isfile():
                    data = archive.extractfile(entry).read()
                    if any(value.encode() in data for value in sensitive if value):
                        raise RuntimeError('credential_leak_detected')
                    hashes[entry.name] = hashlib.sha256(data).hexdigest()
        if proc.wait(timeout=20):
            raise RuntimeError('candidate_scan_failed')
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()
    return hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offline-preflight', action='store_true')
    parser.add_argument('--catalog-only', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to(HERE / 'raw')
    out.mkdir(parents=True, exist_ok=False)
    tag = 'codex-boundary-' + secrets.token_hex(5)
    nets, containers = [], []
    broker, candidate = tag + '-broker', tag + '-candidate'
    internal, egress = tag + '-internal', tag + '-egress'
    broker_process = None
    nonce = 'session-' + secrets.token_urlsafe(32)
    result = dict(status='STARTED', benchmark_trials=0, api_key_used=False, real_credentials_read=False,
                  model='gpt-6.1-sol', agent_budget_seconds=240, broker_lifetime_seconds=300, response_quota=12,
                  automatic_retries=False)
    sensitive = []
    for name in ['account_broker.py','live_probe.py']:
        (out/name).write_bytes((HERE/name).read_bytes())
    try:
        context = out / 'image'
        context.mkdir()
        shutil.copytree(HARBOR / 'generated/pilot-live-fixed/environment/codex-bundle', context / 'codex-bundle')
        (context / 'Dockerfile').write_text('FROM ' + BASE + '\nCOPY codex-bundle /opt/codex\n'
            'ENV PATH=/opt/pytest-python/bin:/opt/codex/bin:/opt/codex/codex-path:$PATH HOME=/home/agent SHELL=/bin/bash\n'
            'WORKDIR /work\nRUN mkdir -p /home/agent /work /logs && chmod -R a+rX /opt/codex\n')
        image = docker('build', '--network=none', '-q', str(context), timeout=120).stdout.strip()
        result['candidate_image'] = image
        for net, flags in [(internal, ['--internal']), (egress, [])]:
            docker('network', 'create', *flags, net); nets.append(net)
        for name, img in [(broker, BASE), (candidate, image)]:
            docker('create','--name',name,'--network',internal,'--user','1000:1000',
                   '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                   '--cpus','2','--memory','4g','--memory-swap','4g','--pids-limit','128','--log-driver','none',
                   '--ulimit','core=0:0',
                   '--tmpfs','/work:rw,exec,nosuid,nodev,size=128m,uid=1000,gid=1000',
                   '--tmpfs','/tmp:rw,exec,nosuid,nodev,size=256m,uid=1000,gid=1000',
                   '--tmpfs','/logs:rw,nosuid,nodev,size=32m,uid=1000,gid=1000',
                   '--tmpfs','/home/agent:rw,exec,nosuid,nodev,size=64m,uid=1000,gid=1000',
                   img,'sleep','420')
            containers.append(name)
            docker('start',name)
        docker('network','connect',egress,broker)
        for name in containers:
            info = json.loads(docker('inspect',name).stdout)[0]
            assert not info['Mounts'] and not info['HostConfig']['Binds']
            assert info['HostConfig']['CapDrop']==['ALL'] and info['HostConfig']['ReadonlyRootfs']
            assert info['HostConfig']['PidMode'] != 'host' and not info['HostConfig']['Privileged']
            assert not info['HostConfig']['PortBindings']
            if name == candidate:
                assert list(info['NetworkSettings']['Networks']) == [internal]
            else:
                ip = info['NetworkSettings']['Networks'][internal]['IPAddress']
            save(out / (name.rsplit('-',1)[1]+'-inspection.json'), info)
        assert json.loads(docker('network','inspect',internal).stdout)[0]['Internal']
        boundary_script = '''import pathlib,socket,json,os
assert not any(pathlib.Path(p).exists() for p in ['/base','/Users/junyuc/.codex/auth.json','/var/run/docker.sock','/tmp/account_broker.py'])
for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try: assert b'/tmp/account_broker.py' not in p.read_bytes().split(bytes([0]))
 except PermissionError:pass
s=socket.socket();s.settimeout(2)
try:s.connect(('1.1.1.1',443));raise AssertionError('public egress reachable')
except (OSError,TimeoutError):pass
finally:s.close()
print('ISOLATION_PREFLIGHT_PASS')
'''
        assert 'ISOLATION_PREFLIGHT_PASS' in docker('exec', candidate, '/usr/local/bin/python','-I','-c',boundary_script).stdout
        result['isolation_preflight'] = 'PASS'
        result['native_version'] = docker('exec',candidate,'codex','--version').stdout.strip()
        assert result['native_version'] == 'codex-cli 0.162.1'
        upload(candidate,'/work/arithmetic.py','def add(a, b):\n    return a - b\n')
        upload(candidate,'/work/test_arithmetic.py','from arithmetic import add\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-2, 3) == 1\n')
        save(out / 'before-candidate-hashes.json',scan(candidate,[]))
        inventory_script = """import os,json,hashlib
items={}
for root,dirs,files in os.walk('/'):
 dirs[:]=[d for d in dirs if os.path.join(root,d) not in ['/proc','/sys','/dev'] and not os.path.islink(os.path.join(root,d))]
 for name in files:
  p=os.path.join(root,name)
  try:
   if os.path.islink(p):items[p]={'link':os.readlink(p)}
   elif os.path.isfile(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
     for block in iter(lambda:f.read(1048576),b''):h.update(block)
    items[p]={'sha256':h.hexdigest()}
  except OSError:items[p]={'unreadable':True}
print(json.dumps(items))
"""
        inventory = json.loads(docker('exec',candidate,'/usr/local/bin/python','-I','-c',inventory_script,timeout=60).stdout)
        assert not any('/.codex/auth.json' in p or '/pytest_5786/' in p or '/iteration/' in p for p in inventory)
        save(out/'initial-filesystem-inventory.json',inventory)
        result['initial_filesystem_entries']=len(inventory)
        if args.offline_preflight:
            result['status'] = 'OFFLINE_PREFLIGHT_PASS'
            return
        # Main account file is read only on the trusted host, never copied/mounted.
        auth_path = Path('/Users/junyuc/.codex/auth.json')
        auth_bytes = auth_path.read_bytes()
        auth = json.loads(auth_bytes)
        tokens = auth['tokens']
        assert not auth.get('OPENAI_API_KEY') and auth.get('auth_mode') == 'chatgpt'
        access = tokens['access_token']
        payload = json.loads(base64.urlsafe_b64decode(access.split('.')[1] + '==='))
        assert payload['exp'] > time.time() + 360, 'account_token_expiring_no_refresh_attempted'
        sensitive = [tokens[k] for k in ['access_token','refresh_token','id_token'] if tokens.get(k)]
        result['real_credentials_read'] = True
        result['account_token_valid_for_probe'] = True
        upload(broker,'/tmp/account_broker.py',(HERE/'account_broker.py').read_text())
        # Anonymous stdin pipe, not argv/env/file/Docker mount. Only the access token
        # and non-secret account selector enter the dedicated trusted process.
        audit_file = (out/'broker-audit.jsonl').open('w')
        broker_process = subprocess.Popen([*DOCKER,'exec','-i',broker,'/usr/local/bin/python','-I','-u','/tmp/account_broker.py'],
                                          stdin=subprocess.PIPE,stdout=audit_file,stderr=subprocess.DEVNULL,text=True)
        broker_process.stdin.write(json.dumps(dict(nonce=nonce,access_token=access,account_id=tokens['account_id']))+'\n')
        broker_process.stdin.flush(); broker_process.stdin.close()
        for _ in range(50):
            if '"ready"' in (out/'broker-audit.jsonl').read_text():break
            time.sleep(.1)
        else:raise RuntimeError('broker_not_ready')
        docker('exec',candidate,'mkdir','-p','/home/agent/.codex')
        enc=lambda x:base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip('=')
        jwt=enc({'alg':'none'})+'.'+enc({'https://api.openai.com/auth':{'chatgpt_account_id':'synthetic-candidate','chatgpt_plan_type':'plus'}})+'.synthetic'
        placeholder=dict(auth_mode='chatgpt',OPENAI_API_KEY=None,tokens=dict(id_token=jwt,access_token=nonce,refresh_token='NOT-REFRESHABLE',account_id='synthetic-candidate'),last_refresh=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        upload(candidate,'/home/agent/.codex/auth.json',json.dumps(placeholder))
        config = ('chatgpt_base_url = "http://'+ip+':8765"\nweb_search = "disabled"\nmodel_provider = "account_boundary"\n'
            '[model_providers.account_boundary]\nname = "Isolated Codex account"\nbase_url = "http://'+ip+':8765/backend-api/codex"\n'
            'wire_api = "responses"\nrequires_openai_auth = true\nrequest_max_retries = 0\nstream_max_retries = 0\n'
            '[features]\nplugins = false\napps = false\nremote_plugin = false\nskill_search = false\nskill_mcp_dependency_install = false\nmulti_agent = false\nenable_request_compression = false\n')
        upload(candidate,'/home/agent/.codex/config.toml',config)
        negative_script = """import http.client,json,pathlib
nonce=json.loads(pathlib.Path('/home/agent/.codex/auth.json').read_text())['tokens']['access_token']
cases=[('wrong_nonce','/backend-api/codex/responses','wrong',401),('auth_file','/auth.json',nonce,404),('arbitrary_host','https://example.com/',nonce,404)]
result={}
for name,path,key,expected in cases:
 c=http.client.HTTPConnection(HOST,8765,timeout=5)
 c.request('POST',path,json.dumps({'model':'gpt-6.1-sol'}),{'Authorization':'Bearer '+key})
 r=c.getresponse();assert r.status==expected;result[name]=r.status;r.read();c.close()
print(json.dumps(result))
""".replace('HOST',repr(ip))
        save(out/'live-negative-checks.json',json.loads(docker('exec',candidate,'python','-c',negative_script).stdout))
        check = "import http.client,json,pathlib;c=http.client.HTTPConnection("+repr(ip)+",8765,timeout=130);n=json.loads(pathlib.Path('/home/agent/.codex/auth.json').read_text())['tokens']['access_token'];c.request('GET','/backend-api/codex/models?client_version=0.162.1',headers={'Authorization':'Bearer '+n});r=c.getresponse();print(r.status);r.read();assert r.status==200"
        catalog = docker('exec',candidate,'python','-c',check,check=False,timeout=140)
        result['catalog_check_exit']=catalog.returncode
        result['catalog_status']=catalog.stdout.strip()
        assert catalog.returncode==0, 'catalog_failed_before_model'
        result['login_status'] = docker('exec',candidate,'codex','login','status').stderr.strip()
        save(out/'pre-model-candidate-hashes.json',scan(candidate,sensitive))
        if args.catalog_only:
            result['status']='CATALOG_PASS'
            result['credential_scan']='PASS' if scan(candidate,sensitive) else 'EMPTY'
            return
        started=time.monotonic()
        run = docker('exec','-w','/work',candidate,'codex','exec','--dangerously-bypass-approvals-and-sandbox',
                     '--skip-git-repo-check','--model','gpt-6.1-sol','--json','--enable','unified_exec','--',PROMPT,
                     check=False,timeout=240)
        result['agent_seconds']=round(time.monotonic()-started,3)
        result['codex_exit_code']=run.returncode
        if any(x in run.stdout+run.stderr for x in sensitive):raise RuntimeError('credential_output_leak')
        (out/'native-codex.jsonl').write_text(run.stdout)
        (out/'native-codex.stderr').write_text(run.stderr)
        save(out/'post-model-candidate-hashes.json',scan(candidate,sensitive))
        result['credential_scan']='PASS: writable files and process environments, before/after; logs'
        result['auth_file_unchanged']=auth_path.read_bytes()==auth_bytes
        audit=[json.loads(x) for x in (out/'broker-audit.jsonl').read_text().splitlines()]
        result['upstream_response_requests']=sum(x.get('route')=='responses' and x.get('kind')=='upstream_started' for x in audit)
        result['upstream_statuses']=[x['status'] for x in audit if x.get('kind')=='upstream']
        assert run.returncode==0 and 'turn.completed' in run.stdout, 'native_run_failed_no_retry'
        assert any(x.get('selected_model_present') for x in audit), 'selected_model_catalog_not_verified'
        # Verification is controller-owned and independent of the model's claim.
        verify=docker('exec','-w','/work',candidate,'python','-c',
                      'from arithmetic import add;assert add(2,3)==5;assert add(-2,3)==1;assert add(0,0)==0;print("SOURCE_CHECK_PASS")')
        result['source_verification']=verify.stdout.strip()
        tests=docker('exec','-w','/work',candidate,'python','-m','pytest','-q','test_arithmetic.py')
        (out/'verification.txt').write_text(tests.stdout+tests.stderr)
        (out/'arithmetic.py').write_text(docker('exec',candidate,'cat','/work/arithmetic.py').stdout)
        # Destruction of trusted broker is session revocation; same nonce loses route.
        assert docker('rm','-f',broker).returncode==0
        containers.remove(broker)
        revoked=docker('exec',candidate,'python','-c',
                       "import socket;s=socket.socket();s.settimeout(2);r=s.connect_ex(("+repr(ip)+",8765));assert r!=0;print('REVOKED')")
        result['revocation_check']=revoked.stdout.strip()
        result['status']='LIVE_ACCOUNT_BOUNDARY_PASS'
    except Exception as error:
        result['status']='VALIDATION_FAILED'
        result['failure_type']=type(error).__name__
        import traceback
        result['failure_lines']=[{'file':Path(t.filename).name,'line':t.lineno} for t in traceback.extract_tb(error.__traceback__)]
        # Exception values are deliberately not persisted (third-party may include secrets).
    finally:
        for name in reversed(containers):
            result.setdefault('cleanup',[]).append({'container':name,'removed':docker('rm','-f',name,check=False).returncode==0})
        if broker_process:
            try:broker_process.wait(timeout=10)
            except subprocess.TimeoutExpired:broker_process.kill();broker_process.wait()
        for net in reversed(nets):
            result.setdefault('cleanup',[]).append({'network':net,'removed':docker('network','rm',net,check=False).returncode==0})
        save(out/'result.json',result)
        print(json.dumps(result,indent=2))
    return 0 if result['status']=='LIVE_ACCOUNT_BOUNDARY_PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
