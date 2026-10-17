"""Harbor Docker lifecycle with a fixed network and frozen, bounded handoff."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess

from harbor.environments.base import ExecResult
from harbor.environments.docker.docker import _sanitize_docker_compose_project_name
from colima import ColimaEnvironment
from common import docker, load_runtime, save
from snapshot import extract


class PilotEnvironment(ColimaEnvironment):
    def __init__(self, *args, **kwargs):
        token = hashlib.sha256(str(kwargs['trial_paths'].trial_dir).encode()).hexdigest()[:12]
        kwargs['session_id'] = 'pilot-' + token + '-' + kwargs['session_id']
        super().__init__(*args, **kwargs)

    @staticmethod
    def _requires_egress_control(*, startup_network_policy, phase_network_policies):
        # Use Docker's network=none, not an in-container network-policy sidecar.
        # No dynamic transitions or hostname allowlists are supported here.
        modes = {p.network_mode.value for p in [startup_network_policy, *phase_network_policies]}
        if len(modes) != 1 or not modes <= {'public', 'no-network'}:
            raise ValueError('Pilot requires one fixed network policy per container')
        return False

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={'disable_internet': True})

    async def _apply_network_policy(self, network_policy):
        if network_policy != self.network_policy:
            raise ValueError('Dynamic network changes are not supported')
        self.inspect_policy()

    def inspect(self):
        return json.loads(subprocess.check_output(docker('inspect', self.cid)))[0]

    def inspect_policy(self):
        info = self.inspect()
        h = info['HostConfig']
        if hasattr(self, 'evidence'):
            save(self.evidence / 'effective-policy.json', {k:info[k] for k in ('Id','Image','HostConfig','Mounts','State')})
        assert not h['Privileged'] and not h.get('Binds') and not info['Mounts']
        assert not h.get('Devices') and not h.get('PortBindings') and not h.get('VolumesFrom')
        assert h['ReadonlyRootfs'] and h['CapDrop'] == ['ALL'] and {c.removeprefix('CAP_') for c in h['CapAdd']} == {'KILL'}
        assert 'no-new-privileges' in h['SecurityOpt']
        assert h['Memory'] == h['MemorySwap'] == 4096 * 1024 * 1024
        assert h['NanoCpus'] == 2000000000 and h['PidsLimit'] == 128
        assert not h['PidMode'] and h['IpcMode'] == 'private'
        assert h['LogConfig']['Type'] == 'none'
        expected = 'none' if self.network_policy.network_mode.value == 'no-network' else 'bridge'
        assert h['NetworkMode'] == expected
        assert set(h['Tmpfs']) == {'/work', '/tmp', '/logs', '/home/agent'}
        return {k: info[k] for k in ('Id', 'Image', 'HostConfig', 'Mounts', 'State')}

    async def start(self, force_build=False):
        await super().start(force_build)
        result = await self._run_docker_compose_command(['ps', '-q', 'main'])
        self.cid = result.stdout.strip()
        self.frozen = False
        self.captured = None
        self.evidence = self.trial_paths.trial_dir / ('verifier-environment' if '__verifier__' in self.session_id else 'agent-environment')
        self.evidence.mkdir(parents=True, exist_ok=True)
        save(self.evidence / 'docker-inspect.json', self.inspect_policy())
        result = await self.exec(command='cp -R --preserve=mode /base/. /work/', user='1000:1000')
        assert result.return_code == 0
        self.default_user = '1000:1000'

    async def _collect_buffered_output(self, process, timeout_sec=None, stdin_data=None):
        return await self._collect_limited(process, timeout_sec, stdin_data)

    async def _run_docker_compose_command(self, command, check=True, timeout_sec=None,
                                          stdin_data=None, on_output=None):
        # Same Harbor 0.24 command construction, with an owned process group so
        # killing the Docker CLI also closes its Compose plugin's transport.
        runtime = type(self).runtime()
        argv = [*runtime.compose, '--project-name', _sanitize_docker_compose_project_name(self.session_id)]
        if runtime.supports_compose_project_directory:
            argv += ['--project-directory', str(self.environment_dir.resolve())]
        for path in self._docker_compose_paths:
            argv += ['-f', str(path.resolve())]
        process = await asyncio.create_subprocess_exec(*argv, *command,
            env=self._compose_env_vars(include_os_env=True), cwd=self.environment_dir,
            start_new_session=True, stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        result = await self._collect_limited(process, timeout_sec, stdin_data)
        if check and result.return_code:
            # Do not echo potentially sensitive exec argv or output in errors.
            if command[0] != 'exec':
                self.logger.error('Docker %s failed: %s', command[0], result.stdout[-2000:])
            raise RuntimeError('Docker '+command[0]+' failed with code '+str(result.return_code))
        return result

    async def _collect_streamed_output(self, process, timeout_sec=None, stdin_data=None, on_output=None):
        # Native Codex JSONL is retained on disk; callbacks are not needed for
        # this supervised pilot. Cap transport instead of buffering indefinitely.
        return await self._collect_limited(process, timeout_sec, stdin_data)

    async def _collect_limited(self, process, timeout_sec, stdin_data):
        async def capture():
            if stdin_data is not None:
                process.stdin.write(stdin_data)
                await process.stdin.drain()
                process.stdin.close()
            data = bytearray()
            while chunk := await process.stdout.read(65536):
                data.extend(chunk)
                if len(data) > 16 * 1024 * 1024:
                    raise RuntimeError('Harbor command output exceeded 16 MiB')
            code = await process.wait()
            return ExecResult(return_code=code, stdout=data.decode(errors='replace'), stderr='')
        try:
            return await asyncio.wait_for(capture(), timeout=timeout_sec or 1800)
        except BaseException:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.communicate()
            # docker exec transport termination is not candidate termination.
            # Harbor's AGENT_END hook quiesces it; startup errors are cleaned by stop.
            raise

    def copy_archive(self, source, label, limit):
        load_runtime()
        from core import bounded
        # Docker cp cannot read this daemon's tmpfs mounts. Use the immutable
        # system interpreter only AFTER all candidate uid processes are dead.
        program = ('import sys,tarfile; '
                   't=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); '
                   't.add(sys.argv[1],arcname=sys.argv[2],recursive=True); t.close()')
        record = bounded(docker('exec', '-u', '0', self.cid, '/usr/local/bin/python', '-I', '-c',
                                program, source, Path(source).name), self.evidence,
                         dict(os.environ), 30, self.evidence / label, output_limit=limit)
        if record['returncode'] or record['timeout'] or record['output_limit_exceeded']:
            raise RuntimeError('Frozen Docker archive failed or exceeded budget')
        return Path(record['stdout'])

    async def freeze(self):
        if self.frozen:
            return
        self.inspect_policy()
        program = Path(__file__).with_name('quiesce.py').read_text()
        result = await self.exec(command='/usr/local/bin/python -I -c ' + shlex.quote(program), user='root', timeout_sec=15)
        if result.return_code:
            raise RuntimeError('Candidate quiescence/source metadata check failed: ' + result.stdout[-1000:])
        observation = json.loads(result.stdout)
        source = self.copy_archive('/work/src', 'source-tar', 20 * 1024 * 1024)
        self.captured = self.evidence / 'captured'
        inventory = extract(source, self.captured)
        assert inventory == observation['source'], 'Archive differs from stopped-process inode audit'
        logs = self.copy_archive('/logs/agent', 'logs-tar', 34 * 1024 * 1024)
        extract(logs, self.evidence / 'logs', source=False)
        save(self.evidence / 'handoff.json', dict(candidate_processes_stopped=True,
             collection='immutable system Python as controller-only root, after uid 1000 termination',
             container_id=self.cid, source=inventory,
             source_archive_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
        self.frozen = True

    async def download_dir(self, source_dir, target_dir):
        if not getattr(self, 'frozen', False):
            # Never let recovery paths invoke the stock unbounded archive reader.
            Path(target_dir).mkdir(parents=True, exist_ok=True)
            return
        if self.frozen:
            target = Path(target_dir)
            target.mkdir(parents=True, exist_ok=True)
            if str(source_dir).rstrip('/') == '/logs/agent':
                shutil.copytree(self.evidence / 'logs/agent', target, dirs_exist_ok=True)
            elif str(source_dir).rstrip('/') != '/logs/artifacts':
                raise ValueError('Unexpected download after source freeze')
            # Arbitrary /logs/artifacts is deliberately not trusted or transferred.
            return
        return await super().download_dir(source_dir, target_dir)

    async def upload_file(self, source_path, target_path):
        # Docker cp cannot write into this daemon's read-only-root + tmpfs layout.
        # Write as the intended uid through the immutable interpreter, never
        # place file contents in argv, error messages, or controller captures.
        data = Path(source_path).read_bytes()
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Upload exceeds 2 MiB')
        script = ('import os,sys; '
                  'fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600); '
                  'f=os.fdopen(fd,"wb"); f.write(sys.stdin.buffer.read(2097153)); f.close()')
        process = await asyncio.create_subprocess_exec(
            *docker('exec','-i','-u',self.default_user or '0',self.cid,
                    '/usr/local/bin/python','-I','-c',script,str(target_path)),
            start_new_session=True, stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        result = await self._collect_limited(process, 30, data)
        if result.return_code:
            raise RuntimeError('Bounded file upload failed')

    async def stop(self, delete=True):
        cid = getattr(self, 'cid', None)
        await super().stop(delete)
        if cid:
            found = subprocess.run(docker('inspect', cid), capture_output=True)
            if found.returncode == 0:
                raise RuntimeError('Harbor container cleanup failed')
            save(self.evidence / 'cleanup.json', dict(container_id=cid, removed=True))
