"""Single Docker/Colima candidate boundary. No host mounts, credentials or network.

This module does not open the agent gate: its real probes must pass first, followed
by Linux Eval qualification and a separately verified Codex remote-tool route.
"""
import json
from pathlib import Path
import re
import secrets

from core import InfrastructureError, bounded, save
from handoff import read_bytes

MIB = 1024 * 1024


def create_command(docker, endpoint, client_config, name, image, script,
                   memory_mib=4096, pids=128, disk_mib=2048):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise InfrastructureError('A locally resolved immutable image ID is required')
    if not re.fullmatch(r'pytest5786-[0-9a-f]{24}', name):
        raise InfrastructureError('Invalid owned container name')
    if not endpoint.startswith('unix:///'):
        raise InfrastructureError('Only the explicitly selected local VM socket is supported')
    if not (64 <= memory_mib <= 4096 and 8 <= pids <= 128 and 8 <= disk_mib <= 2048):
        raise InfrastructureError('Container limits exceed the single-Eval policy')
    # /dev/shm is a second writable tmpfs: include it in the total storage budget.
    shm = 1
    return [docker, '--host', endpoint, '--config', str(client_config), 'create',
            '--interactive', '--name', name, '--label', 'pytest5786.owner='+name,
            '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--user', '1000:1000', '--init',
            '--memory', str(memory_mib*MIB), '--memory-swap', str(memory_mib*MIB),
            '--pids-limit', str(pids), '--cpus', '2', '--shm-size', str(shm*MIB),
            '--tmpfs', '/trial:rw,nosuid,nodev,size='+str((disk_mib-shm)*MIB)+',mode=700,uid=1000,gid=1000',
            '--workdir', '/trial', '--env', 'HOME=/trial', '--env', 'TMPDIR=/trial',
            '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'PYTHONNOUSERSITE=1',
            '--log-driver', 'none', '--entrypoint', '/usr/local/bin/python', image, '-I', '-c', script]


def validate_inspection(info, name, image, memory_mib=4096, pids=128, disk_mib=2048):
    """Inspect the created object before allowing any candidate process to start."""
    h, c = info['HostConfig'], info['Config']
    expected_tmpfs = '/trial:rw,nosuid,nodev,size='+str((disk_mib-1)*MIB)+',mode=700,uid=1000,gid=1000'
    valid = (info['Image'] == image and c.get('User') == '1000:1000'
        and c.get('Labels', {}).get('pytest5786.owner') == name
        and h.get('NetworkMode') == 'none' and h.get('ReadonlyRootfs') is True
        and h.get('Privileged') is False and not h.get('Binds') and not h.get('Devices')
        and not h.get('PortBindings') and not h.get('VolumesFrom')
        and not h.get('CapAdd') and h.get('CapDrop') == ['ALL']
        and 'no-new-privileges' in h.get('SecurityOpt', [])
        and h.get('Memory') == memory_mib*MIB and h.get('MemorySwap') == memory_mib*MIB
        and h.get('PidsLimit') == pids and h.get('NanoCpus') == 2000000000
        and h.get('ShmSize') == MIB and h.get('Init') is True
        and h.get('Tmpfs') == {'/trial': expected_tmpfs.split(':',1)[1]}
        and h.get('LogConfig', {}).get('Type') == 'none'
        and h.get('PidMode', '') == '' and h.get('IpcMode') == 'private'
        and not info.get('Mounts'))
    if not valid:
        raise InfrastructureError('Effective container policy differs from the required boundary')


class DockerBoundary:
    def __init__(self, docker, endpoint, client_config, image, output):
        self.docker, self.endpoint, self.image = str(docker), endpoint, image
        self.config = Path(client_config).absolute()
        self.config.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.output = Path(output).absolute()
        self.output.mkdir(parents=True)
        self.counter = 0
        self.env = {'PATH':'/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin',
                    'HOME':str(self.output), 'DOCKER_CONFIG':str(self.config)}

    def command(self, *args):
        return [self.docker,'--host',self.endpoint,'--config',str(self.config),*map(str,args)]

    def call(self, label, *args, timeout=15):
        self.counter += 1
        return bounded(self.command(*args),self.output,self.env,timeout,
                       self.output/('%03d-%s'%(self.counter,label)))

    def inspect(self, identifier):
        record = self.call('inspect','inspect',identifier)
        if record['returncode'] != 0:
            raise InfrastructureError('Could not inspect owned container')
        return json.loads(read_bytes(record['stdout']))[0]

    def run(self, script, label, timeout=10, output_limit=1024*1024, input_text=None, **limits):
        name = 'pytest5786-'+secrets.token_hex(12)
        identifier = None
        receipt = {'status':'infrastructure_failure','name':name,'image':self.image,'model_calls':0}
        try:
            command = create_command(self.docker,self.endpoint,self.config,name,self.image,script,**limits)
            record = bounded(command,self.output,self.env,20,self.output/(label+'-create'))
            if record['returncode'] != 0:
                raise InfrastructureError('Container creation failed; see controller capture')
            identifier = read_bytes(record['stdout']).decode().strip()
            if not re.fullmatch('[0-9a-f]{64}',identifier):
                raise InfrastructureError('Docker did not return a full container identity')
            receipt['container_id'] = identifier
            info = self.inspect(identifier)
            if info['Config'].get('Labels',{}).get('pytest5786.owner') != name:
                raise InfrastructureError('Container owner label mismatch')
            validate_inspection(info, name, self.image, **limits)
            receipt['effective_host_config'] = info['HostConfig']
            receipt['effective_mounts'] = info['Mounts']
            execution = bounded(self.command('start','--attach','--interactive',identifier),self.output,self.env,timeout,
                                self.output/(label+'-execution'),input_text=input_text,output_limit=output_limit)
            receipt['execution'] = execution
            receipt['status'] = 'completed'
        finally:
            # Creation can succeed even if the client disconnects before returning its ID.
            # Recover only this unpredictable invocation-owned name, then check its label.
            if identifier is None:
                recovery = self.call('recover', 'inspect', name)
                if recovery['returncode'] == 0:
                    recovered = json.loads(read_bytes(recovery['stdout']))[0]
                    if recovered['Config'].get('Labels', {}).get('pytest5786.owner') != name:
                        raise InfrastructureError('Refusing recovery of an unowned container')
                    identifier = recovered['Id']
            if identifier is not None:
                # Stop the entire PID namespace, not merely docker start's host group.
                info = self.inspect(identifier)
                if info['Config'].get('Labels',{}).get('pytest5786.owner') != name:
                    raise InfrastructureError('Refusing cleanup of a container not owned by this probe')
                if info['State']['Running']:
                    kill = self.call('kill','kill',identifier)
                    if kill['returncode'] != 0:
                        raise InfrastructureError('Owned container did not accept termination')
                final = self.inspect(identifier)
                receipt['final_state'] = final['State']
                receipt['all_candidate_processes_stopped'] = not final['State']['Running'] and final['State']['Pid'] == 0
                if not receipt['all_candidate_processes_stopped']:
                    raise InfrastructureError('Owned container still has a running PID namespace')
                removed = self.call('remove','rm',identifier)
                receipt['removed'] = removed['returncode'] == 0
                if not receipt['removed']:
                    raise InfrastructureError('Owned container cleanup failed')
            save(self.output/(label+'-receipt.json'),receipt)
        return receipt


RESOURCE_PROGRAM = r'''
import errno,json,os,socket,subprocess,sys,time
from pathlib import Path
r={}
for key in ('memory.max','memory.swap.max','pids.max','cpu.max'):
    r[key]=Path('/sys/fs/cgroup',key).read_text().strip()
try: Path('/host-write-canary').write_text('fake')
except OSError as e: r['root_read_only']=e.errno in (errno.EROFS,errno.EACCES)
else: r['root_read_only']=False
try:
    s=socket.socket();s.settimeout(.5);s.connect(('1.1.1.1',443))
except OSError as e: r['network_unreachable']=e.errno in (errno.ENETUNREACH,errno.EACCES,errno.EPERM)
else: r['network_unreachable']=False
finally: s.close()
children=[]
try:
    for _ in range(24):
        try: children.append(subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)']))
        except OSError as e:
            r['pid_limit_enforced']=e.errno==errno.EAGAIN;break
finally:
    for child in children: child.kill()
    for child in children: child.wait()
r['spawned_children']=len(children)
try:
    with open('/trial/quota-test','wb',buffering=0) as f:
        for _ in range(10): f.write(b'x'*(1024*1024))
except OSError as e: r['disk_limit_enforced']=e.errno==errno.ENOSPC
else: r['disk_limit_enforced']=False
Path('/trial/quota-test').unlink()
# Each child is below 128 MiB; combined resident allocation exceeds the cgroup.
children=[subprocess.Popen([sys.executable,'-c','import time;a=bytearray(80*1024*1024);time.sleep(2)']) for _ in range(2)]
r['memory_children_exit']=[p.wait() for p in children]
r['memory_events']=Path('/sys/fs/cgroup/memory.events').read_text()
r['aggregate_memory_enforced']=int(dict(x.split() for x in r['memory_events'].splitlines()).get('oom_kill','0'))>0
print(json.dumps(r),flush=True)
'''


def resource_probe(boundary):
    receipt=boundary.run(RESOURCE_PROGRAM,'resources',memory_mib=128,pids=16,disk_mib=8,timeout=20)
    if receipt['execution']['returncode'] != 0:
        raise InfrastructureError('Finite container resource probe did not complete')
    results=json.loads(read_bytes(receipt['execution']['stdout']))
    required=['root_read_only','network_unreachable','pid_limit_enforced','disk_limit_enforced','aggregate_memory_enforced']
    if not all(results.get(k) is True for k in required) or results['memory.max']!=str(128*MIB) or results['memory.swap.max']!='0' or results['pids.max']!='16':
        raise InfrastructureError('Container resource enforcement did not match the declared limits')
    for label,delay in [('normal',0),('timeout',20)]:
        program="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True);print(p.pid,flush=True);time.sleep("+str(delay)+")"
        child=boundary.run(program,label,timeout=1 if delay else 10)
        if not child['all_candidate_processes_stopped'] or bool(delay)!=child['execution']['timeout']:
            raise InfrastructureError('Detached child cleanup probe failed')
    fresh=boundary.run("from pathlib import Path; assert not Path('/trial/previous-trial').exists(); Path('/trial/previous-trial').write_text('disposable')", 'fresh-trial',timeout=5)
    if fresh['execution']['returncode'] or not fresh['all_candidate_processes_stopped']:
        raise InfrastructureError('Fresh container state check failed')
    again=boundary.run("from pathlib import Path; assert not Path('/trial/previous-trial').exists()", 'fresh-trial-reset',timeout=5)
    if again['execution']['returncode'] or not again['all_candidate_processes_stopped']:
        raise InfrastructureError('Prior trial state survived a new container')
    capped=boundary.run("import sys,time;sys.stdout.write('x'*20000);sys.stdout.flush();time.sleep(20)", 'output-cap',timeout=5,output_limit=4096)
    if not capped['execution']['output_limit_exceeded'] or not capped['all_candidate_processes_stopped']:
        raise InfrastructureError('Container output limit probe failed')
    save(boundary.output/'resource_results.json',{'status':'PASSED','observations':results,'model_calls':0})
    return results
