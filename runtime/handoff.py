"""Small macOS/POSIX fd-based handoff. Never follow worker-controlled path components."""
import json
import math
import os
from pathlib import Path
import secrets
import stat

from core import InfrastructureError

OBSERVATION_LIMIT = 1024 * 1024
CAPTURE_LIMIT = 8 * 1024 * 1024


def canonical_path(path):
    """Only expand macOS's fixed OS aliases; do not resolve arbitrary symlinks."""
    path = Path(path).absolute()
    if '..' in path.parts:
        raise InfrastructureError('Handoff path contains a parent traversal')
    for alias in ('tmp', 'var'):
        if path.parts[1:2] == (alias,):
            path = Path('/private').joinpath(*path.parts[1:])
    return path


class Directory:
    """Pin every directory via openat(O_DIRECTORY|O_NOFOLLOW), including the root."""
    def __init__(self, path, create=False, trusted=False):
        self.path = canonical_path(path)
        self.fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in self.path.parts[1:]:
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=self.fd)
                    except FileExistsError:
                        pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=self.fd)
                os.close(self.fd)
                self.fd = child
                info = os.fstat(child)
                if trusted:
                    # Same-UID worker protection comes from Seatbelt, not chmod.
                    # Reject other-user/group mutable ancestry; allow system sticky
                    # temp ancestors, but never a sticky capture directory itself.
                    sticky_parent = bool(info.st_mode & stat.S_ISVTX) and component != self.path.name
                    if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not sticky_parent):
                        raise InfrastructureError('Controller output has unsafe directory ownership or permissions')
        except (OSError, InfrastructureError):
            self.close()
            raise InfrastructureError('Handoff directory is missing, linked or inaccessible') from None
        self.identity = self._identity(os.fstat(self.fd))

    @staticmethod
    def _identity(st):
        return st.st_dev, st.st_ino

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def unchanged(self):
        with Directory(self.path) as current:
            if current.identity != self.identity:
                raise InfrastructureError('Handoff directory was replaced')

    @staticmethod
    def basename(name):
        if not name or name in ('.', '..') or '/' in name:
            raise InfrastructureError('Handoff expects a single file name')

    def read(self, name, limit, missing_ok=False):
        self.basename(name)
        self.unchanged()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise InfrastructureError('Handoff output is missing') from None
        except OSError:
            raise InfrastructureError('Handoff output cannot be safely opened') from None
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise InfrastructureError('Handoff output must be a single-link regular file')
            if before.st_size > limit:
                raise InfrastructureError('Handoff output exceeds byte limit')
            chunks, size = [], 0
            while size <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk); size += len(chunk)
            if size > limit:
                raise InfrastructureError('Handoff output exceeds byte limit')
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if signature(before) != signature(after) or signature(after) != signature(named):
                raise InfrastructureError('Handoff output changed during capture')
            self.unchanged()
            return b''.join(chunks)
        except OSError:
            raise InfrastructureError('Handoff output changed or could not be read') from None
        finally:
            os.close(fd)

    def write(self, name, data):
        """Atomic publication, never truncate/follow an existing target or hard link."""
        self.basename(name)
        self.unchanged()
        try:
            existing = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1):
            raise InfrastructureError('Controller output target is not a single-link regular file')
        temp = '.handoff-' + secrets.token_hex(16)
        fd = None
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self.fd)
            with os.fdopen(fd, 'wb') as stream:
                fd = None
                stream.write(data)
            self.unchanged()
            # Even a late replacement of name is replaced as a directory entry, never followed.
            os.replace(temp, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        except OSError:
            raise InfrastructureError('Controller output could not be safely published') from None
        finally:
            if fd is not None: os.close(fd)
            try: os.unlink(temp, dir_fd=self.fd)
            except FileNotFoundError: pass

    def verify_capture(self, name, stream):
        self.unchanged()
        try:
            opened = os.fstat(stream.fileno())
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if (not stat.S_ISREG(named.st_mode) or opened.st_nlink != 1
                    or self._identity(opened) != self._identity(named)):
                raise InfrastructureError('Controller capture path was replaced')
        except OSError:
            raise InfrastructureError('Controller capture path was replaced') from None

    def capture(self, name):
        """Create a fresh controller pipe sink, failing on all pre-existing entries."""
        self.basename(name)
        self.unchanged()
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self.fd)
        except OSError:
            raise InfrastructureError('Controller capture target already exists or is unsafe') from None
        return os.fdopen(fd, 'wb')


def read_bytes(path, limit=CAPTURE_LIMIT, missing_ok=False):
    path = canonical_path(path)
    with Directory(path.parent) as parent:
        return parent.read(path.name, limit, missing_ok)


def write_bytes(path, data):
    path = canonical_path(path)
    with Directory(path.parent, create=True, trusted=True) as parent:
        parent.write(path.name, data)


def observation(data, method):
    """Validate the existing check.py envelope without changing scoring semantics."""
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('duplicate key')
            value[key] = item
        return value
    def nonfinite(_):
        raise ValueError('nonfinite')
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
        valid = (type(value) is dict
                 and type(value.get('schema_version')) is int and value['schema_version'] == 1
                 and value.get('method') == method
                 and type(value.get('tests_run')) is int and value['tests_run'] == 1
                 and value.get('status') in ('passed','failed','error','skipped'))
        if not valid:
            raise ValueError('invalid envelope')
        duration = value['duration_seconds']
        if not (type(duration) in (int,float) and math.isfinite(duration) and duration >= 0):
            raise ValueError('invalid duration')
        for name in ('failures','skips'):
            if not (type(value[name]) is list and all(type(x) is str for x in value[name])):
                raise ValueError('invalid message list')
        if not (type(value['details']) is list and all(type(x) is dict for x in value['details'])):
            raise ValueError('invalid details')
    except (ValueError, UnicodeError, KeyError, TypeError, RecursionError, OverflowError):
        # Never echo rejected JSON, arbitrary exception text or file contents.
        raise InfrastructureError('Worker observation has invalid JSON or required fields') from None
    return value
