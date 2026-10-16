"""Trusted single-eval operations and bounded subprocess capture (stdlib only)."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

BASE = '955e54221008aba577ecbaefa15679f6777d3bf8'


class InfrastructureError(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def clean_env(workspace, scratch, python):
    scratch = Path(scratch)
    for name in ['home', 'tmp']:
        (scratch / name).mkdir(parents=True, exist_ok=True)
    return {'PATH': str(Path(python).parent) + ':/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'HOME': str(scratch / 'home'), 'TMPDIR': str(scratch / 'tmp'),
            'PYTHONPATH': str(Path(workspace) / 'src'), 'PYTHONHASHSEED': '0',
            'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'COLUMNS': '80', 'TERM': 'dumb',
            'PY_COLORS': '0', 'LC_ALL': 'C', 'TZ': 'UTC',
            'EVAL_WORKSPACE': str(workspace), 'EVAL_SCRATCH': str(scratch),
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull,
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_OPTIONAL_LOCKS': '0'}


def git_env(cwd):
    return {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'HOME': '/nonexistent-runtime-home',
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull,
            'GIT_CEILING_DIRECTORIES': str(Path(cwd).resolve().parent),
            'PYTHONDONTWRITEBYTECODE': '1', 'LC_ALL': 'C'}


def git(cwd, *args):
    return subprocess.check_output(['git', '-c', 'core.hooksPath=' + os.devnull,
            '-c', 'core.attributesFile=' + os.devnull, '-c', 'core.autocrlf=false',
            '-C', str(cwd), *map(str, args)], env=git_env(cwd), stderr=subprocess.PIPE)


def bounded(command, cwd, env, timeout, log_prefix, input_text=None, output_limit=8*1024*1024):
    """Own process group, deadline, combined byte cap; never log the environment."""
    prefix = Path(log_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    result = {'command': list(map(str, command)), 'cwd': str(cwd),
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'timeout': False, 'output_limit_exceeded': False, 'returncode': None,
              'stdout': str(prefix.with_suffix('.stdout')), 'stderr': str(prefix.with_suffix('.stderr'))}
    input_file = prefix.with_suffix('.stdin')
    if input_text is not None:
        input_file.write_text(input_text)
    process = None
    def stop():
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                if process.poll() is None:
                    result['cleanup_error'] = str(exc)
                    try:
                        process.kill()
                    except OSError as kill_error:
                        result['direct_kill_error'] = str(kill_error)
                else:
                    # macOS may report EPERM for an already vanished process group.
                    result['post_exit_group_signal_error'] = str(exc)
    try:
        with open(input_file if input_text is not None else os.devnull, 'rb') as source, \
             open(result['stdout'], 'wb') as stdout, open(result['stderr'], 'wb') as stderr:
            process = subprocess.Popen(result['command'], cwd=str(cwd), env=env,
                                       stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True)
            selector = selectors.DefaultSelector()
            for pipe, dest in [(process.stdout, stdout), (process.stderr, stderr)]:
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, dest)
            total = 0
            killed_at = None
            # EOF is not process exit: a command can close both pipes and keep working.
            # Reap the direct child before post-exit group cleanup, avoiding macOS's
            # transient EPERM on a disappearing group between EOF and waitpid.
            while selector.get_map() or process.poll() is None:
                elapsed = time.monotonic() - start
                if elapsed >= timeout and killed_at is None:
                    result['timeout'] = True
                    stop()
                    killed_at = time.monotonic()
                if process.poll() is not None and killed_at is None:
                    stop()  # kill ordinary descendants even when the direct child exits first
                    killed_at = time.monotonic()
                if killed_at is not None and time.monotonic() - killed_at > 2:
                    result['descendant_pipe_leak'] = True
                    break
                for key, _ in selector.select(.05):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = max(0, output_limit - total)
                    key.data.write(chunk[:remaining])
                    total += len(chunk)
                    if total > output_limit and not result['output_limit_exceeded']:
                        result['output_limit_exceeded'] = True
                        stop()
                        killed_at = time.monotonic()
            selector.close()
            stop()
            try:
                result['returncode'] = process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                result['cleanup_error'] = 'Owned child did not terminate after kill'
            result['output_bytes_seen'] = total
    except OSError as exc:
        result['launch_error'] = str(exc)
    finally:
        stop()
        if process is not None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                result['cleanup_error'] = 'Owned child did not terminate after kill'
            for stream in [process.stdout, process.stderr]:
                stream.close()
        result['elapsed_seconds'] = time.monotonic() - start
        result['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(prefix.with_suffix('.execution.json'), result)
    return result


class Package:
    def __init__(self, root, repo):
        self.root = Path(root).resolve()
        self.repo = Path(repo).resolve()
        self.task = json.loads((self.root / 'task.yaml').read_text())
        self.environment = json.loads((self.root / 'environment.yaml').read_text())
        if self.task['eval_id'] != 'pytest_5786' or self.task['repository']['base_commit'] != BASE:
            raise InfrastructureError('This runtime supports only pytest_5786 at its declared fixed base')
        self.lock = json.loads((self.root / 'checksums.json').read_text())
        for name, expected in self.lock['files'].items():
            if sha(self.root / name) != expected:
                raise InfrastructureError('Eval checksum mismatch: ' + name)
        self.files = json.loads((self.root / 'base_files.json').read_text())
        resolved = git(self.repo, 'rev-parse', '--verify', BASE + '^{commit}').decode().strip()
        if resolved != BASE:
            raise InfrastructureError('Required base object is unavailable')
        self.provenance = {'eval_id': self.task['eval_id'], 'eval_version': self.task['eval_version'],
                           'eval_commit': git(self.root.parent, 'rev-parse', 'HEAD').decode().strip(),
                           'eval_lock_sha256': sha(self.root / 'checksums.json'),
                           'source_base_commit': BASE,
                           'runtime_source_sha256': {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
                           'eval_worktree_status': git(self.root.parent, 'status', '--porcelain').decode()}
        # Load only verified trusted controller code; never import candidate source here.
        spec = importlib.util.spec_from_file_location('pytest5786_private_grader', self.root / 'private/grader.py')
        self.grader = importlib.util.module_from_spec(spec)
        old = list(sys.path)
        try:
            spec.loader.exec_module(self.grader)
        finally:
            sys.path[:] = old

    def prepare(self, destination):
        dest = Path(destination).absolute()
        subprocess.run([sys.executable, '-B', str(self.root / 'prepare.py'), '--repo', str(self.repo),
                        '--destination', str(dest)], env=git_env(dest), check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        extras = {'TASK.md', 'eval_public.json', 'eval_public/test_example.py',
                  'eval_requirements.txt', 'src/_pytest/_version.py'}
        actual = {str(p.relative_to(dest)) for p in dest.rglob('*') if p.is_file() and '.git' not in p.relative_to(dest).parts}
        if actual != set(self.files) | extras or any(sha(dest/n) != h for n,h in self.files.items()):
            raise InfrastructureError('Export manifest/payload mismatch')
        if git(dest, 'status', '--porcelain') or git(dest, 'remote') or git(dest, 'rev-list', '--all', '--count').strip() != b'1':
            raise InfrastructureError('Export Git baseline is not clean and isolated')
        if (dest/'.git/objects/info/alternates').exists() or any(p.is_symlink() for p in (dest/'.git').rglob('*')):
            raise InfrastructureError('Export shares external Git objects')
        return git(dest, 'rev-parse', 'HEAD').decode().strip()
