"""Source-only collection through a pristine controller-owned Git mirror."""
import os
from pathlib import Path
import re
import stat

from core import InfrastructureError, git, sha, save


def source_files(workspace, rejected):
    source = Path(workspace)/'src'
    if source.is_symlink() or not source.is_dir():
        raise rejected('src must be an ordinary directory')
    paths = {}
    excluded = []
    for root, directories, files in os.walk(source, followlinks=False):
        for name in directories:
            path = Path(root)/name
            if path.is_symlink():
                raise rejected('Symlink directory: '+str(path.relative_to(workspace)))
        for name in files:
            path = Path(root)/name
            rel = str(path.relative_to(workspace))
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise rejected('Nonregular or multiply linked source: '+rel)
            if not rel.endswith('.py'):
                excluded.append(rel)
                continue
            if not re.fullmatch(r'src/[A-Za-z0-9_./-]+\.py', rel) or any(p.startswith('.') for p in Path(rel).parts):
                raise rejected('Invalid source path: '+rel)
            paths[rel] = path
    return paths, excluded


def collect(package, workspace, baseline, destination):
    """Called only after participant processes are stopped. Never invoke Git in its tree."""
    workspace, destination = Path(workspace), Path(destination)
    destination.mkdir(parents=True)
    mirror = destination/'mirror'
    restored = package.prepare(mirror)
    if restored != baseline:
        raise InfrastructureError('Recorded synthetic baseline does not match reconstructed baseline')
    reject = package.grader.RejectedPatch
    candidate, excluded = source_files(workspace, reject)
    initial, _ = source_files(mirror, reject)
    for rel, path in candidate.items():
        expected_mode = stat.S_IMODE(initial[rel].stat().st_mode) if rel in initial else 0o644
        if stat.S_IMODE(path.stat().st_mode) != expected_mode:
            raise reject('Changed source mode or non-0644 new source: '+rel)
    shim = 'src/_pytest/_version.py'
    if shim not in candidate or candidate[shim].read_bytes() != initial[shim].read_bytes():
        raise reject('Generated version shim was modified or removed')
    candidate.pop(shim)
    initial.pop(shim)
    total = 0
    for rel in sorted(set(candidate) | set(initial)):
        target = mirror/rel
        if rel not in candidate:
            target.unlink()
        else:
            file = candidate[rel]
            # Limits bound collection memory/work; source tree is tiny and participant is stopped.
            total += file.stat().st_size
            if file.stat().st_size > 2*1024*1024 or total > 16*1024*1024:
                raise reject('Source collection exceeds runtime size budget')
            descriptor = os.open(file, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                with os.fdopen(descriptor, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise reject('Source changed during collection')
                    content = stream.read(2*1024*1024+1)
            except Exception:
                raise
            try:
                content.decode('utf-8')
            except UnicodeError:
                raise reject('Source must be UTF-8: '+rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(stat.S_IMODE(initial[rel].stat().st_mode) if rel in initial else 0o644)
    # Pristine attributes/config only: candidate .git, .gitattributes, hooks and tests are never copied.
    git(mirror, 'add', '--all', '--', 'src')
    patch = destination/'submission.patch'
    patch.write_bytes(git(mirror, 'diff', '--cached', '--no-renames', '--no-ext-diff', '--no-textconv', '--binary', baseline, '--', 'src'))
    changed = package.grader.validate_patch(patch)
    # Inventory outside src without following symlinks; never open those bytes.
    observed = set()
    for root, directories, files in os.walk(workspace, followlinks=False):
        directories[:] = [d for d in directories if not (Path(root)==workspace and d in ['src','.git'])]
        for directory in directories:
            if (Path(root)/directory).is_symlink():
                excluded.append(str((Path(root)/directory).relative_to(workspace)))
        for name in files:
            path = Path(root)/name
            rel = str(path.relative_to(workspace))
            observed.add(rel)
            original = mirror/rel
            info = path.lstat()
            if not original.is_file() or not stat.S_ISREG(info.st_mode) or info.st_size > 2*1024*1024:
                excluded.append(rel)
            elif stat.S_IMODE(info.st_mode) != stat.S_IMODE(original.stat().st_mode):
                excluded.append(rel)
            else:
                with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
                    content = stream.read(2*1024*1024+1)
                if content != original.read_bytes():
                    excluded.append(rel)
    excluded += [name for name in package.files if not name.startswith('src/') and name not in observed]
    result = {'status': 'accepted', 'patch': str(patch), 'patch_sha256': sha(patch),
              'changed_files': changed, 'excluded_files': sorted(set(excluded)),
              'source_sha256': {n: sha(mirror/n) if (mirror/n).exists() else None for n in changed},
              'agent_git_metadata_ignored': True,
              'synthetic_baseline_commit': baseline}
    save(destination/'submission.json', result)
    return result


def assert_applied(package, patch, workspace, expected=None):
    paths = package.grader.validate_patch(Path(patch))
    if not paths:
        if expected not in (None, {}):
            raise InfrastructureError('Empty patch has a nonempty expected source inventory')
        return {}
    for check in [True, False]:
        applied = package.grader.git_apply(Path(patch), Path(workspace), check=check)
        if applied.returncode:
            raise package.grader.RejectedPatch(applied.stderr)
    actual = {n: sha(Path(workspace)/n) if (Path(workspace)/n).exists() else None for n in paths}
    if expected is not None and actual != expected:
        raise InfrastructureError('Applied bytes differ from collected source inventory')
    return actual
