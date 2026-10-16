"""Codex native Seatbelt execution; never falls back to host execution."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import sys

from core import InfrastructureError, bounded, clean_env, save, sha
from handoff import Directory, canonical_path, read_bytes


class NativeSandbox:
    def __init__(self, codex, python, controller):
        self.codex = str(Path(codex).resolve())
        self.python = str(Path(python).absolute())  # keep venv symlink semantics
        self.controller = Path(controller).absolute()
        self.controller.mkdir(parents=True, exist_ok=True)
        version = bounded([self.codex, '--version'], self.controller,
                          {'PATH':'/usr/bin:/bin','HOME':str(self.controller)}, 10, self.controller/'codex-version')
        if version['returncode'] != 0:
            raise InfrastructureError('Codex CLI is unavailable')
        self.identity = {'version':Path(version['stdout']).read_text().strip(),
                         'executable':self.codex, 'executable_sha256':sha(self.codex)}
        self.git = '/Library/Developer/CommandLineTools/usr/bin/git'
        if sys.platform != 'darwin' or not Path(self.git).is_file():
            raise InfrastructureError('This MVP requires macOS and the installed CommandLineTools Git')
        # Only trusted interpreter startup, with no candidate cwd/PYTHONPATH.
        result = bounded([self.python, '-I', '-c', 'import sys; print(sys.base_prefix)'],
                         self.controller, {'PATH': '/usr/bin:/bin'}, 10, self.controller/'interpreter')
        if result['returncode'] != 0:
            raise InfrastructureError('Cannot locate trusted historical Python runtime')
        self.base_prefix = Path(result['stdout']).read_text().strip()
        self.venv = str(Path(self.python).parent.parent)
        self.readable = [self.venv, self.base_prefix, self.git, str(Path(__file__).with_name('worker.py'))]
        self.features = {'wall_deadline': True, 'output_byte_cap': True, 'process_group_cleanup': True,
                         'per_process_cpu_seconds': True, 'per_file_size_bytes': True,
                         'aggregate_memory': False, 'per_trial_process_count': False,
                         'aggregate_disk_quota': False, 'cpu_core_allocation': False,
                         'detached_descendant_containment': False}

    def permissions(self, workspace, scratch, read_only=(), controller_outputs=()):
        fs = {':root': 'deny', ':minimal': 'read', ':tmpdir': 'deny', ':slash_tmp': 'deny'}
        for name in self.readable + list(map(str, read_only)):
            fs[name] = 'read'
        # Exact per-run scratch; never permit its parent or global tmp.
        fs[str(canonical_path(scratch))] = 'write'
        for name in [self.controller, *controller_outputs]:
            fs[str(canonical_path(name))] = 'deny'
        return '{ trial = { extends = ":workspace", filesystem = { ' + ', '.join(
            json.dumps(k) + ' = ' + json.dumps(v) for k,v in fs.items()) + ' }, network = { enabled = false } } }'

    def execute(self, command, cwd, env, timeout, log_prefix, read_only=(), output_limit=8*1024*1024):
        scratch = canonical_path(env['EVAL_SCRATCH'])
        capture = canonical_path(log_prefix).parent
        # Parent paths are opened without links; no worker write root may
        # contain a controller output directory (including its parents).
        for protected in (capture, canonical_path(self.controller)):
            with Directory(protected, create=True, trusted=True):
                pass
            for writable in (canonical_path(cwd), scratch):
                if protected == writable or writable in protected.parents:
                    raise InfrastructureError('Controller outputs overlap a worker-writable root')
        policy = self.permissions(cwd, scratch, read_only, [capture])
        limit = {'cpu_seconds': max(2, int(timeout) * 2), 'file_bytes': 32*1024*1024}
        args = [self.codex, 'sandbox', '-P', 'trial', '-C', str(cwd), '-c', 'permissions=' + policy,
                '--', '/usr/bin/env', '-i']
        args += [k+'='+v for k,v in sorted(env.items())]
        # Isolated bootstrap ignores candidate PYTHONPATH/sitecustomize until limits exist.
        args += [self.python, '-I', str(Path(__file__).with_name('worker.py')), json.dumps(limit), *map(str, command)]
        result = bounded(args, cwd, {'PATH': '/usr/bin:/bin', 'HOME': str(self.controller)},
                         timeout, log_prefix, output_limit=output_limit)
        result['policy'] = policy
        result['policy_sha256'] = hashlib.sha256(policy.encode()).hexdigest()
        result['limits'] = limit
        result['worker_started'] = b'PYTEST5786_WORKER_READY\n' in read_bytes(result['stderr'])
        result['log'] = result['stdout']
        save(Path(log_prefix).with_suffix('.execution.json'), result)
        if not result['worker_started'] or result.get('launch_error'):
            raise InfrastructureError('Isolated worker failed to start; see ' + result['stderr'])
        if result['output_limit_exceeded'] or result.get('descendant_pipe_leak') or result.get('cleanup_error'):
            raise InfrastructureError('Worker output/cleanup containment failure; see ' + result['stderr'])
        return result

    def resource_probe(self, workspace, folder):
        folder = Path(folder)
        folder.mkdir(parents=True)
        env = clean_env(workspace, folder/'scratch', self.python)
        program = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(8)']); print(p.pid,flush=True); time.sleep(8)"
        result = self.execute([self.python,'-c',program],workspace,env,.5,folder/'timeout')
        if not result['timeout'] or result['returncode']!=-9 or result.get('descendant_pipe_leak'):
            raise InfrastructureError('Native owned-child termination probe failed')
        try:
            self.execute([self.python,'-c',"import sys,time;sys.stdout.write('x'*20000);sys.stdout.flush();time.sleep(8)"],
                         workspace,env,5,folder/'output-cap',output_limit=4096)
        except InfrastructureError:
            capped = json.loads((folder/'output-cap.execution.json').read_text())
            if not capped['output_limit_exceeded'] or capped['returncode']!=-9 or capped.get('cleanup_error'):
                raise
        else:
            raise InfrastructureError('Native output cap was not enforced')
        save(folder/'result.json', {'status':'passed', 'timeout':result, 'output_cap':capped,
                                   'scope':'ordinary owned process group; not detached/adversarial descendants'})
        return {'status':'passed','evidence':str(folder/'result.json')}

    def canaries(self, workspace, folder, read_only=(), git_checks=True, readonly_canary=None):
        folder = Path(folder)
        folder.mkdir(parents=True)
        controller = folder / 'private'
        controller.mkdir()
        config = {}
        for name in ['private', 'other_trial', 'credentials', 'outside_write']:
            target = controller/name
            target.write_text('FAKE_' + name)
            config[name] = str(target)
        # A unique shared-temp canary, never data from another real trial.
        import tempfile
        fd, name = tempfile.mkstemp(prefix='pytest5786-cross-trial-', dir='/private/tmp')
        os.write(fd, b'FAKE_SHARED_TMP')
        os.close(fd)
        config['shared_tmp'] = name
        config['git'] = self.git
        config['git_checks'] = git_checks
        config['limited_worker'] = True
        if readonly_canary is not None:
            assert Path(readonly_canary).is_file()
            config['readonly_canary'] = str(readonly_canary)
        assert all(Path(config[n]).is_file() for n in ['private','other_trial','credentials','outside_write','shared_tmp'])
        scratch = folder/'scratch'
        env = clean_env(workspace, scratch, self.python)
        shutil.copyfile(Path(__file__).with_name('canary.py'), scratch/'canary.py')
        save(scratch/'canaries.json', config)
        save(folder/'canary_existence.json', {k: str(v) for k,v in config.items()})
        try:
            result = self.execute([self.python, str(scratch/'canary.py'), str(scratch/'canaries.json')],
                                  workspace, env, 15, folder/'probe', read_only)
            observations = json.loads(Path(result['stdout']).read_text())
            save(folder/'observations.json', observations)
            if result['returncode'] != 0 or not all(item['passed'] for item in observations.values()):
                raise InfrastructureError('Canary enforcement/usability failed: '+str(folder/'observations.json'))
            return observations
        finally:
            Path(name).unlink()  # only the exact fake file created above

    def environment(self, workspace, folder):
        folder = Path(folder)
        folder.mkdir(parents=True)
        env = clean_env(workspace, folder/'scratch', self.python)
        program = "import sys,json,pytest,pkg_resources,tempfile; from pathlib import Path; assert sys.version_info[:3]==(3,8,20); reqs=[pkg_resources.Requirement.parse(x) for x in Path('eval_requirements.txt').read_text().splitlines()]; assert all(pkg_resources.get_distribution(r.project_name) in r for r in reqs); assert Path(pytest.__file__).resolve()==Path.cwd()/'src/pytest.py'; f=tempfile.TemporaryFile(); f.close(); print(json.dumps({'python':sys.version,'pytest_file':pytest.__file__,'dependencies':{r.project_name:pkg_resources.get_distribution(r.project_name).version for r in reqs}}))"
        record = self.execute([self.python, '-c', program], workspace, env, 15, folder/'preflight')
        if record['returncode'] != 0:
            raise InfrastructureError('Historical environment preflight failed')
        fingerprint = json.loads(Path(record['stdout']).read_text())
        for label, extra in [('serial', []), ('xdist', ['-p', 'xdist.plugin', '-n', '1'])]:
            command = [self.python, '-m', 'pytest', '-o', 'addopts=', '-p', 'no:cacheprovider', '-vv', *extra, 'eval_public/test_example.py']
            result = self.execute(command, workspace, env, 30, folder/label)
            text = Path(result['stdout']).read_text()
            wanted = [11,12,13,21,22,23] if label=='serial' else [13,23]
            if result['returncode'] != 1 or '2 failed' not in text or not all('ValueError: '+str(n) in text for n in wanted):
                raise InfrastructureError('Public baseline reproducer failed runtime contract: '+label)
            if label=='xdist' and ('gw0' not in text or any('ValueError: '+str(n) in text for n in [11,12,21,22])):
                raise InfrastructureError('Xdist baseline worker/chain signature mismatch')
        result = self.execute([self.python, '-m', 'pytest', '-o', 'addopts=', '-p', 'no:cacheprovider', '-p', 'pytester', '-q',
                               'testing/test_reports.py::TestReportSerialization::test_collectreport_passed'], workspace, env, 30, folder/'sanity')
        if result['returncode'] != 0:
            raise InfrastructureError('Historical public sanity test failed')
        save(folder/'environment.json', fingerprint)
        return fingerprint
