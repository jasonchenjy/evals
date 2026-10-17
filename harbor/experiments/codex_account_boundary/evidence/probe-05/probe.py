"""Bounded fake-account compatibility probe; no live mode, credentials or upstream.

Two disposable containers on one internal Docker network. Existing fixed Pilot
candidate image, native Codex 0.162.1, local deterministic Responses only.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
HARBOR = HERE.parents[1]
sys.path.insert(0, str(HARBOR / 'pilot'))
from tool_fixture import commands as tool_commands

IMAGE = 'sha256:c8fdaf8d4e214181d34d3f5623b2e1ff19d354dc4129916043b86e9d27448901'
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///private/tmp/pytest5786-colima/default/docker.sock', '--config', str(HARBOR / 'tools/docker')]


def docker(*args, check=True, timeout=30, input_text=None):
    result = subprocess.run([*DOCKER, *args], capture_output=True, text=True, timeout=timeout, input=input_text)
    if check and result.returncode:
        raise RuntimeError('Docker operation failed: ' + args[0] + '; ' + result.stderr[-700:])
    return result


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def upload(source, container, target):
    # Docker cp cannot populate this daemon's tmpfs behind a read-only rootfs.
    docker('exec', '-i', container, '/usr/local/bin/python', '-I', '-c',
           'import sys,pathlib;pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())',
           target, input_text=source.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to(HERE / 'raw')
    out.mkdir(parents=True, exist_ok=False)
    tag = 'codex-auth-probe-' + secrets.token_hex(6)
    net = tag + '-net'
    broker = tag + '-broker'
    candidate = tag + '-candidate'
    containers = []
    created_network = False
    nonce = 'probe-' + secrets.token_urlsafe(24)
    account = 'SYNTHETIC-ACCOUNT-' + secrets.token_hex(24)
    result = {'status': 'RUNNING', 'real_model_calls': 0, 'real_credentials_read': False,
              'api_key_used': False, 'image': IMAGE, 'native_version_expected': '0.162.1'}
    for source in (HERE / 'probe.py', HERE / 'offline_broker.py'):
        (out / source.name).write_bytes(source.read_bytes())
    result['probe_code_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (HERE / 'probe.py', HERE / 'offline_broker.py')}
    try:
        docker('image', 'inspect', IMAGE)
        docker('network', 'create', '--internal', net)
        created_network = True
        for name in (broker, candidate):
            docker('create', '--name', name, '--network', net, '--user', '1000:1000',
                   '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--cpus', '2', '--memory', '4g', '--memory-swap', '4g', '--pids-limit', '128',
                   '--log-driver', 'none', '--tmpfs', '/work:rw,exec,nosuid,nodev,size=1536m,uid=1000,gid=1000',
                   '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=256m,uid=1000,gid=1000',
                   '--tmpfs', '/logs:rw,exec,nosuid,nodev,size=128m,uid=1000,gid=1000',
                   '--tmpfs', '/home/agent:rw,exec,nosuid,nodev,size=64m,uid=1000,gid=1000',
                   IMAGE, 'sleep', '360')
            containers.append(name)
            docker('start', name)
            inspect = json.loads(docker('inspect', name).stdout)[0]
            assert not inspect['Mounts'] and not inspect['HostConfig']['Binds']
            assert inspect['HostConfig']['CapDrop'] == ['ALL']
            assert inspect['HostConfig']['ReadonlyRootfs']
            save(out / (name.rsplit('-', 1)[-1] + '-inspection.json'), inspect)
        ip = json.loads(docker('inspect', broker).stdout)[0]['NetworkSettings']['Networks'][net]['IPAddress']
        state = out / 'synthetic-state.json'
        save(state, {'nonce': nonce, 'upstream_secret': account})
        isolation = '''import pathlib,os,json,socket
paths=['/tmp/probe-state.json','/Users/junyuc/.codex/auth.json','/var/run/docker.sock']
assert all(not pathlib.Path(p).exists() for p in paths)
auth=json.loads(pathlib.Path('/home/agent/.codex/auth.json').read_text())
assert auth.get('auth_mode')=='chatgpt' and not auth.get('OPENAI_API_KEY')
assert auth['tokens']['access_token'].startswith('probe-')
for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try: assert b'offline_broker.py' not in p.read_bytes()
 except PermissionError: pass
print('ACCOUNT_BOUNDARY_OK: session placeholder only; no upstream credential files/processes')
'''
        import shlex
        check = 'text(await tools.exec_command(' + json.dumps({'cmd': 'python -c ' + shlex.quote(isolation), 'login': False, 'max_output_tokens': 500}) + '));'
        commands = out / 'commands.json'
        save(commands, [check, *tool_commands])
        for source, destination in [(state, '/tmp/probe-state.json'), (commands, '/tmp/commands.json'), (HERE / 'offline_broker.py', '/tmp/offline_broker.py')]:
            upload(source, broker, destination)
        docker('exec', '-d', broker, '/usr/local/bin/python', '-I', '/tmp/offline_broker.py')
        docker('exec', candidate, 'cp', '-R', '--preserve=mode', '/base/.', '/work/')
        docker('exec', candidate, 'mkdir', '-p', '/home/agent/.codex')
        claims = {'https://api.openai.com/auth': {'chatgpt_account_id': 'synthetic-candidate', 'chatgpt_plan_type': 'plus'}}
        enc = lambda x: base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip('=')
        jwt = enc({'alg': 'none'}) + '.' + enc(claims) + '.synthetic'
        auth = out / 'synthetic-client-auth.json'
        save(auth, {'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
                    'tokens': {'id_token': jwt, 'access_token': nonce, 'refresh_token': 'SYNTHETIC-NOT-REFRESHABLE', 'account_id': 'synthetic-candidate'},
                    'last_refresh': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        config = out / 'client-config.toml'
        config.write_text('chatgpt_base_url = "http://' + ip + ':8765"\nweb_search = "disabled"\n'
                          'model_provider = "account_boundary"\n'
                          '[model_providers.account_boundary]\nname = "Account boundary offline probe"\n'
                          'base_url = "http://' + ip + ':8765/backend-api/codex"\n'
                          'wire_api = "responses"\nrequires_openai_auth = true\nrequest_max_retries = 0\nstream_max_retries = 0\n'
                          '[features]\nplugins = false\napps = false\nremote_plugin = false\nskill_search = false\n'
                          'skill_mcp_dependency_install = false\nmulti_agent = false\nenable_request_compression = false\n')
        upload(auth, candidate, '/home/agent/.codex/auth.json')
        upload(config, candidate, '/home/agent/.codex/config.toml')
        checks = '''import http.client,json,pathlib
token=json.loads(pathlib.Path('/home/agent/.codex/auth.json').read_text())['tokens']['access_token']
cases=[('wrong_nonce','POST','/backend-api/codex/responses',{'model':'gpt-6.1-sol'},'wrong',{},401),
('credential_endpoint','GET','/auth.json',None,token,{},404),
('arbitrary_route','POST','/other',{'model':'gpt-6.1-sol'},token,{},404),
('wrong_model','POST','/backend-api/codex/responses',{'model':'unapproved'},token,{},403),
('encoded_body','POST','/backend-api/codex/responses',{'model':'gpt-6.1-sol'},token,{'Content-Encoding':'gzip'},400),
('oversized','POST','/backend-api/codex/responses',{'model':'gpt-6.1-sol'},token,{'Content-Length':str(3*1024*1024)},413)]
out={}
for name,method,path,body,credential,extra,expected in cases:
 c=http.client.HTTPConnection(HOST,8765,timeout=5)
 headers={'Authorization':'Bearer '+credential,**extra}
 c.request(method,path,body=json.dumps(body) if body else None,headers=headers)
 r=c.getresponse();out[name]=r.status;assert r.status==expected,(name,r.status);r.read();c.close()
print(json.dumps(out))
'''.replace('HOST', repr(ip))
        negative = docker('exec', candidate, '/usr/local/bin/python', '-I', '-c', checks)
        save(out / 'negative-checks.json', json.loads(negative.stdout))
        status = docker('exec', '-e', 'CODEX_HOME=/home/agent/.codex', candidate, 'codex', 'login', 'status')
        result['native_login_status'] = (status.stdout + status.stderr).strip()
        assert 'ChatGPT' in result['native_login_status']
        run = docker('exec', '-e', 'CODEX_HOME=/home/agent/.codex', candidate,
                     'codex', 'exec', '--dangerously-bypass-approvals-and-sandbox', '--skip-git-repo-check',
                     '--model', 'gpt-6.1-sol', '--json', '--enable', 'unified_exec', '--',
                     'Offline synthetic credential boundary probe. No benchmark task.', check=False, timeout=150)
        (out / 'native-codex.jsonl').write_text(run.stdout)
        (out / 'native-codex.stderr').write_text(run.stderr)
        result['codex_exit_code'] = run.returncode
        for name in ['audit.json', 'tool-outputs.json']:
            data = docker('exec', broker, '/usr/local/bin/python', '-I', '-c', 'from pathlib import Path;print(Path(' + repr('/tmp/' + name) + ').read_text())', check=False)
            if data.returncode == 0:
                (out / name).write_text(data.stdout)
        assert run.returncode == 0, 'Native Codex failed; inspect local evidence, no live retry'
        assert 'turn.completed' in run.stdout and 'ACCOUNT_BOUNDARY_OK' in run.stdout
        assert 'PINNED_ENV_OK' in run.stdout and 'PUBLIC_AND_XDIST_OK' in run.stdout and 'PTY_DONE' in run.stdout
        audit = json.loads((out / 'audit.json').read_text())
        assert sum('upstream_request' in x for x in audit) == 9
        assert all(x.get('account_header_valid', True) and x.get('candidate_nonce_not_forwarded', True) for x in audit)
        scan = docker('exec', candidate, '/usr/local/bin/python', '-I', '-c',
                      "import pathlib,hashlib,json;print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for root in ['/work','/tmp','/logs','/home/agent'] for p in pathlib.Path(root).rglob('*') if p.is_file()}))")
        files = json.loads(scan.stdout)
        assert hashlib.sha256(state.read_bytes()).hexdigest() not in files.values()
        save(out / 'candidate-file-hashes.json', files)
        assert account not in run.stdout + run.stderr + (out / 'tool-outputs.json').read_text()
        docker('exec', broker, '/usr/local/bin/python', '-I', '-c', "from pathlib import Path;Path('/tmp/revoked').touch()")
        revoke = '''import http.client,json,pathlib
token=json.loads(pathlib.Path('/home/agent/.codex/auth.json').read_text())['tokens']['access_token']
c=http.client.HTTPConnection(HOST,8765,timeout=5)
c.request('POST','/backend-api/codex/responses',body=json.dumps({'model':'gpt-6.1-sol'}),headers={'Authorization':'Bearer '+token})
r=c.getresponse();assert r.status==401;print('REVOKED_SESSION_DENIED')
'''.replace('HOST', repr(ip))
        assert 'REVOKED_SESSION_DENIED' in docker('exec', candidate, '/usr/local/bin/python', '-I', '-c', revoke).stdout
        result.update(status='OFFLINE_COMPATIBILITY_PASSED', local_response_requests=9,
                      account_mode=True, upstream_credential_not_in_candidate=True,
                      native_tools_and_public_tests=True, negative_checks_passed=6,
                      revoked_session_denied=True, live_readiness=False)
    except BaseException as error:
        result.update(status='OFFLINE_PROBE_FAILED', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        cleanup = []
        for name in reversed(containers):
            r = docker('rm', '-f', name, check=False)
            cleanup.append({'container': name, 'removed': r.returncode == 0})
        if created_network:
            cleanup.append({'network': net, 'removed': docker('network', 'rm', net, check=False).returncode == 0})
        result['cleanup'] = cleanup
        save(out / 'result.json', result)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
