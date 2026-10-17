"""Trusted deterministic controls using Harbor's BaseAgent interface."""
import shlex
from pathlib import Path
from harbor.agents.nop import NopAgent

class ControlAgent(NopAgent):
    def __init__(self, *args, patch=None, replacement=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.patch = patch
        self.replacement = replacement

    async def setup(self, environment):
        result = await environment.exec(command="hostname; cd /work && git rev-parse HEAD; test ! -e /tests && test ! -e /eval && echo hidden-absent")
        (self.logs_dir / "initial-environment.txt").write_text(str(result))
        if result.return_code:
            raise RuntimeError(str(result))
        probe = "import sys,pkg_resources,pytest; assert sys.version_info[:3]==(3,8,20); assert pytest.__file__.startswith('/work/src/'); reqs=[pkg_resources.Requirement.parse(x) for x in open('/work/eval_requirements.txt')]; assert all(pkg_resources.get_distribution(r.project_name) in r for r in reqs); print(sys.version,pytest.__file__)"
        result = await environment.exec(command="if test -f /work/eval_requirements.txt; then python -c " + shlex.quote(probe) + "; fi")
        (self.logs_dir / "public-preflight.txt").write_text(str(result))
        if result.return_code:
            raise RuntimeError(str(result))

    @staticmethod
    def name():
        return "evals-control"

    async def run(self, instruction, environment, context):
        if self.patch and Path(self.patch).read_bytes().strip():
            await environment.upload_file(Path(self.patch), "/tmp/control.patch")
            command = "cd /work && git apply --whitespace=nowarn /tmp/control.patch"
        elif self.replacement is not None:
            command = "printf %s " + shlex.quote(self.replacement) + " > /work/src/divide.py"
        else:
            command = "true"
        result = await environment.exec(command=command)
        (self.logs_dir / "control.txt").write_text(str(result))
        if result.return_code:
            raise RuntimeError(str(result))
