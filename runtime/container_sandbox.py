"""One Linux/Colima worker adapter, with immutable inputs and byte-only handoff.

The native agent launch gate is deliberately unchanged. This adapter qualifies
Linux candidate execution; it does not verify Codex's remote tool routing.
"""
import base64
import hashlib
import json
from pathlib import Path
import stat

from core import InfrastructureError, bounded, save, sha
from handoff import read_bytes, write_bytes, observation
from container_boundary import DockerBoundary
from sandbox import NativeSandbox

PYTHON = '/opt/pytest-python/bin/python'
BOOTSTRAP = "import runpy;runpy.run_path('/opt/pytest5786-worker/container_worker.py',run_name='__main__')"


def snapshot_files(source):
    """Only controller-owned reconstructed inputs enter the image build context."""
    files, total = {}, 0
    for p in sorted(Path(source).rglob('*')):
        kind = p.lstat().st_mode
        if stat.S_ISDIR(kind):
            continue
        if not stat.S_ISREG(kind):
            raise InfrastructureError('Input snapshot contains a non-regular entry')
        raw = read_bytes(p)
        total += len(raw)
        if total > 64*1024*1024 or len(files) >= 10000:
            raise InfrastructureError('Input snapshot exceeds the single-Eval size limit')
        files[str(p.relative_to(source))] = raw
    return files


def decode_envelope(raw):
    """Validate transport after the entire worker container has been stopped."""
    try:
        value = json.loads(raw)
        if value['schema_version'] != 1 or value['handoff_status'] != 'accepted':
            raise ValueError()
        execution = value['execution']
        if type(execution['returncode']) is not int or type(execution['timeout']) is not bool:
            raise ValueError()
        blobs = {key: None if value[key] is None else base64.b64decode(value[key], validate=True)
                 for key in ('stdout', 'stderr', 'observation')}
        if any(blobs[k] is None for k in ('stdout', 'stderr')):
            raise ValueError()
        if len(blobs['stdout'])+len(blobs['stderr']) > 8*1024*1024:
            raise ValueError()
        if blobs['observation'] is not None and len(blobs['observation']) > 1024*1024:
            raise ValueError()
    except (ValueError, KeyError, TypeError, RecursionError):
        raise InfrastructureError('Container output handoff rejected; no candidate contents included') from None
    return execution, blobs


class ContainerSandbox:
    boundary_name = 'colima-linux-container'
    environment = NativeSandbox.environment  # same public behavior assertions, new executor

    def __init__(self, docker, endpoint, client_config, image, controller):
        self.python = PYTHON
        self.controller = Path(controller).absolute()
        self.controller.mkdir(parents=True)
        self.base = DockerBoundary(docker, endpoint, client_config, image, self.controller/'engine')
        self.cache = {}
        self.calls = 0
        self.features = {'wall_deadline': True, 'output_byte_cap': True,
                         'aggregate_memory': True, 'per_trial_process_count': True,
                         'aggregate_disk_quota': True, 'cpu_core_allocation': True,
                         'detached_descendant_containment': True}
        self.identity = {'boundary': self.boundary_name, 'base_image_id': image,
                         'endpoint': endpoint, 'python': PYTHON}

    def image(self, workspace, read_only):
        files = {'workspace/'+k:v for k,v in snapshot_files(workspace).items()}
        for root in read_only:
            for k,v in snapshot_files(root).items():
                name = 'eval/'+k
                if name in files:
                    raise InfrastructureError('Duplicate immutable worker input')
                files[name] = v
        helpers = ['core.py', 'handoff.py', 'container_worker.py']
        digest = hashlib.sha256(self.base.image.encode())
        for k,v in sorted(files.items()):
            digest.update(k.encode()+b'\0'+hashlib.sha256(v).digest())
        for name in helpers:
            digest.update(read_bytes(Path(__file__).with_name(name)))
        key = digest.hexdigest()
        if key in self.cache:
            return self.cache[key]
        context = self.controller/'images'/key
        context.mkdir(parents=True)
        for name, raw in files.items():
            write_bytes(context/'inputs'/name, raw)
        for name in helpers:
            write_bytes(context/'helpers'/name, read_bytes(Path(__file__).with_name(name)))
        write_bytes(context/'Dockerfile', ('FROM '+self.base.image+'\nCOPY inputs /inputs\nCOPY helpers /opt/pytest5786-worker\nRUN chmod -R a+rX /inputs /opt/pytest5786-worker\n').encode())
        build = bounded(self.base.command('build', '--network', 'none', '--quiet', str(context)),
                        self.controller, self.base.env, 90, context/'build')
        if build['returncode'] != 0:
            raise InfrastructureError('Immutable worker-input image build failed')
        image = read_bytes(build['stdout']).decode().strip().splitlines()[-1]
        if not image.startswith('sha256:') or len(image) != 71:
            raise InfrastructureError('Input image did not return an immutable ID')
        save(context/'manifest.json', {'image':image, 'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}})
        self.cache[key] = image
        return image

    def execute(self, command, cwd, env, timeout, log_prefix, read_only=(), output_limit=8*1024*1024):
        self.calls += 1
        scratch = Path(env['EVAL_SCRATCH'])
        mappings = [(str(cwd), '/trial/workspace'), (str(scratch), '/trial/scratch')]
        mappings += [(str(p), '/inputs/eval') for p in read_only]
        def mapped(value):
            value = str(value)
            for old,new in sorted(mappings, key=lambda x:len(x[0]), reverse=True):
                value = value.replace(old,new)
            return value
        argv = [mapped(x) for x in command]
        runtime_env = {k:mapped(v) for k,v in env.items()}
        runtime_env['PATH'] = '/opt/pytest-python/bin:/usr/local/bin:/usr/bin:/bin'
        image = self.image(cwd, read_only)
        boundary = DockerBoundary(self.base.docker, self.base.endpoint, self.base.config, image,
                                  self.controller/('worker-%03d'%self.calls))
        receipt = boundary.run(BOOTSTRAP, 'worker', timeout=timeout+5, output_limit=16*1024*1024,
                               input_text=json.dumps({'command':argv, 'env':runtime_env, 'timeout':timeout}))
        transport = receipt['execution']
        if not receipt['all_candidate_processes_stopped'] or transport['output_limit_exceeded']:
            raise InfrastructureError('Container transport or cleanup failed')
        if transport['timeout']:
            raise InfrastructureError('Container bootstrap exceeded the worker deadline')
        if transport['returncode'] != 0:
            raise InfrastructureError('Container bootstrap failed before a valid handoff')
        execution, blobs = decode_envelope(read_bytes(transport['stdout'], 16*1024*1024))
        prefix = Path(log_prefix)
        for key in ('stdout','stderr'):
            target = prefix.with_suffix('.'+key)
            write_bytes(target, blobs[key])
            execution[key] = str(target)
        if '--output' in argv and blobs['observation'] is not None:
            method = argv[argv.index('--method')+1]
            validated = observation(blobs['observation'], method)
            # Existing grading adapter reads this controller-owned compatibility file.
            save(scratch/'observation.json', validated)
        execution['container_receipt'] = str(boundary.output/'worker-receipt.json')
        execution['boundary'] = self.boundary_name
        execution['handoff_status'] = 'accepted'
        save(prefix.with_suffix('.execution.json'), execution)
        return execution

    def canaries(self, workspace, folder, read_only=(), git_checks=True, readonly_canary=None):
        from core import clean_env
        folder = Path(folder); folder.mkdir(parents=True)
        import tempfile
        shared = tempfile.NamedTemporaryFile(prefix='pytest5786-other-trial-', dir='/private/tmp', delete=False)
        shared.write(b'FAKE_SHARED_TMP'); shared.close()
        targets = [shared.name]
        for name in ('private','oracle','credentials','other-trial','outside-write'):
            p = folder/name
            p.write_text('FAKE_PRIVATE_CANARY_'+name)
            targets.append(str(p))
        save(folder/'existence.json', {p:Path(p).is_file() for p in targets})
        # These host files really exist. ENOENT in the worker means that its mount
        # namespace does not contain the host paths, not that canaries were omitted.
        program = '''import json,os,pathlib,sys
paths=json.loads(sys.argv[1]);r={}
for p in paths:
 try: open(p,'rb').read(1)
 except OSError: r[p]=True
 else: r[p]=False
 relative=os.path.relpath(p,os.getcwd())
 try: open(relative,'rb').read(1)
 except OSError: r['relative:'+p]=True
 else: r['relative:'+p]=False
try: open(paths[-1],'w').write('overwrite')
except OSError: r['outside_write']=True
else: r['outside_write']=False
p=pathlib.Path('canary.py');p.write_text('# public scratch');r['workspace_rw']=p.read_text()=='# public scratch'
r['socket_absent']=not pathlib.Path('/var/run/docker.sock').exists()
if len(sys.argv)>2:
 q=pathlib.Path(sys.argv[2]);r['immutable_input_readable']=q.read_text()=='immutable fake test input'
 try: q.write_text('modified')
 except OSError: r['immutable_input_write_denied']=True
 else: r['immutable_input_write_denied']=False
print(json.dumps(r))
assert all(r.values())
'''
        env = clean_env(workspace, folder/'scratch', self.python)
        try:
            command = [self.python,'-c',program,json.dumps(targets)]
            if readonly_canary is not None: command.append(str(readonly_canary))
            result = self.execute(command,workspace,env,15,folder/'canary',read_only)
            values = json.loads(read_bytes(result['stdout']))
            unchanged = Path(shared.name).read_bytes() == b'FAKE_SHARED_TMP' and all(Path(p).read_text()=='FAKE_PRIVATE_CANARY_'+Path(p).name for p in targets[1:])
            if result['returncode'] or not all(values.values()) or not unchanged:
                raise InfrastructureError('Container filesystem canary failed')
            save(folder/'observations.json', values)
            return values
        finally:
            Path(shared.name).unlink()
