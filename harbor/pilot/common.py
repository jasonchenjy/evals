"""Single-Eval pilot configuration and read-only reuse of pinned Runtime helpers."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RUNTIME = REPO / "runtime"
HELPERS = ("core.py", "handoff.py", "sandbox.py", "container_boundary.py",
           "container_sandbox.py", "container_worker.py", "grading.py", "submission.py")


def hashes():
    return {n: hashlib.sha256((RUNTIME / n).read_bytes()).hexdigest() for n in HELPERS}


def adapter_hashes():
    paths = list(Path(__file__).parent.glob('*.py')) + [ROOT/'controls.py', ROOT/'colima.py']
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def load_runtime():
    if sys.flags.optimize:
        raise RuntimeError('Pilot security assertions require Python without -O')
    expected = json.loads((Path(__file__).parent / "runtime-lock.json").read_text())
    if hashes() != expected:
        raise RuntimeError("Reused Runtime helpers changed; review and requalify before updating the lock")
    sys.path.insert(0, str(RUNTIME))
    from core import Package
    from container_sandbox import ContainerSandbox
    from grading import grade
    from submission import collect, assert_applied
    if hashes() != expected:
        raise RuntimeError("Runtime changed during import")
    return Package, ContainerSandbox, grade, collect, assert_applied


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def docker(*args):
    return ["/usr/local/bin/docker", "--host", os.environ["DOCKER_HOST"],
            "--config", os.environ["DOCKER_CONFIG"], *map(str, args)]
