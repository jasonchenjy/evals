"""Bounded extraction of a frozen Docker archive; never use tar.extractall."""
import hashlib
from pathlib import Path, PurePosixPath
import re
import tarfile

FILE_LIMIT = 2 * 1024 * 1024
TOTAL_LIMIT = 16 * 1024 * 1024
MAX_ENTRIES = 10000


def normalize_git_modes(snapshot, baseline):
    """Git tracks execute bits, not umask-dependent group write permissions."""
    for p in (Path(snapshot) / 'src').rglob('*.py'):
        reference = Path(baseline) / p.relative_to(snapshot)
        expected = (reference.stat().st_mode & 0o777) if reference.exists() else 0o644
        actual = p.stat().st_mode & 0o7777
        if actual & 0o7111 != expected & 0o111:
            raise ValueError('Source execute/special bits changed')
        p.chmod(expected)


def extract(archive, destination, *, source=True):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    seen, result, total = set(), {}, 0
    with tarfile.open(archive, "r:") as tar:
        for index, member in enumerate(tar):
            name = member.name.rstrip("/")
            parts = PurePosixPath(name).parts
            if (index >= MAX_ENTRIES or not parts or name.startswith("/")
                    or ".." in parts or "." in name.split("/") or "\\" in name
                    or name in seen or "/".join(parts) != name):
                raise ValueError("Unsafe, duplicate or excessive archive path")
            seen.add(name)
            if parts[0] != ("src" if source else "agent"):
                raise ValueError("Archive root mismatch")
            if not (member.isdir() or member.isfile()):
                raise ValueError("Links and special archive entries are forbidden")
            if member.isdir():
                destination.joinpath(*parts).mkdir(parents=True, exist_ok=True)
                continue
            total += member.size
            limit = FILE_LIMIT if source else 16 * 1024 * 1024
            if member.size < 0 or member.size > limit or total > (TOTAL_LIMIT if source else 32 * 1024 * 1024):
                raise ValueError("Archive byte budget exceeded")
            if source and not name.endswith(".py"):
                continue
            if source and (not re.fullmatch(r"src/[A-Za-z0-9_./-]+\.py", name)
                           or any(p.startswith(".") for p in parts)):
                raise ValueError("Invalid source path")
            raw = tar.extractfile(member).read(limit + 1)
            if len(raw) != member.size:
                raise ValueError("Truncated archive member")
            if source:
                raw.decode("utf-8")
            path = destination.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
            path.chmod(member.mode & 0o777)
            result[name] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), mode=member.mode & 0o777)
    if source and not result:
        raise ValueError("Source snapshot is empty")
    return result
