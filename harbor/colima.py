"""Harbor Docker provider for a daemon without host directory sharing.

Retains Harbor lifecycle/network/exec/cp; uses its non-mounted log protocol.
"""
from harbor.environments.docker.docker import DockerEnvironment

class ColimaEnvironment(DockerEnvironment):
    def __init__(self, *args, mounts=None, **kwargs):
        # Harbor injects log binds even for remote daemons. Reject any user mount;
        # only discard its known /logs binds, then rely on Harbor upload/download.
        for mount in mounts or []:
            if mount.get("type") != "bind" or mount["target"] not in {"/logs/agent", "/logs/verifier", "/logs/artifacts"}:
                raise ValueError("Host mounts unsupported by unshared Colima adapter")
        super().__init__(*args, mounts=[], **kwargs)

    async def start(self, force_build=False):
        await super().start(force_build=force_build)
        await self.ensure_dirs(["/logs/agent", "/logs/verifier", "/logs/artifacts"], chmod=True)

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={"mounted": False})
