"""Adapt only execution and input mapping; call the original grader.grade unchanged."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

from core import InfrastructureError, save, sha


def grade(package, sandbox, patch, output, expected_hashes=None):
    output = Path(output).absolute()
    staging = output.parent/(output.name+'-worker-inputs')
    staging.mkdir(parents=True)
    for name in ['private/check.py','private/tests/behavior.py','private/tests/existing_inventory.json','requirements.txt']:
        target = staging/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package.root/name, target)
    (staging/"boundary_canary.txt").write_text("immutable fake test input")
    grader = package.grader
    original_run, original_apply = grader.run, grader.git_apply
    worker_records = []
    boundary_verified = False
    def isolated_run(command, cwd, env, timeout, log):
        nonlocal boundary_verified
        if not boundary_verified:
            sandbox.canaries(cwd, output/"isolation", read_only=[staging], git_checks=False, readonly_canary=staging/"boundary_canary.txt")
            boundary_verified = True
        mapped = [str(x).replace(str(package.root/'private/check.py'), str(staging/'private/check.py'))
                  .replace(str(package.root/'requirements.txt'), str(staging/'requirements.txt')) for x in command]
        env = dict(env)
        env['PATH'] = str(Path(sandbox.python).parent)+':/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin'
        env['GIT_CONFIG_GLOBAL'] = '/dev/null'
        env['GIT_CONFIG_SYSTEM'] = '/dev/null'
        env['GIT_CONFIG_NOSYSTEM'] = '1'
        result = sandbox.execute(mapped, cwd, env, timeout, log, [staging])
        # Preserve a combined log at the original advertised grader path as well.
        Path(log).write_text(Path(result['stdout']).read_text()+Path(result['stderr']).read_text())
        result['log'] = str(log)
        worker_records.append(result)
        return result
    def verified_apply(candidate, workspace, check=False):
        result = original_apply(candidate, workspace, check)
        if not check and not result.returncode and Path(candidate).resolve()==Path(patch).resolve() and expected_hashes is not None:
            actual = {n: sha(Path(workspace)/n) if (Path(workspace)/n).exists() else None for n in expected_hashes}
            if actual != expected_hashes:
                raise InfrastructureError('Grading applied-byte verification failed')
        return result
    grader.run, grader.git_apply = isolated_run, verified_apply
    args = SimpleNamespace(repo=package.repo, python=Path(sandbox.python), patch=Path(patch).absolute(),
                           output=output, trusted_local=True)
    # This flag only enters the legacy trusted orchestration. Every Python execution is
    # replaced above; it is NEVER used as an isolation mechanism or a host fallback.
    inherited_git = {k:v for k,v in os.environ.items() if k.startswith("GIT_")}
    for key in inherited_git:
        del os.environ[key]
    try:
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = grader.grade(args)
    finally:
        grader.run, grader.git_apply = original_run, original_apply
        os.environ.update(inherited_git)
    (output/'controller.stdout').write_text(captured.getvalue())
    result = json.loads((output/'result.json').read_text())
    save(output/'runtime_execution.json', {'boundary': 'codex-native-seatbelt',
          'original_security_mode_label': result['security_mode'], 'all_python_calls_intercepted': True,
          'worker_execution_count': len(worker_records), 'returncode': code,
          'input_files': {str(p.relative_to(staging)): sha(p) for p in staging.rglob('*') if p.is_file()},
          'limits': sandbox.features})
    return result
