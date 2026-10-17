"""Native Harbor Codex run/trajectory/auth; no additional root capabilities."""
import shlex
from harbor.agents.installed.codex import Codex


class PilotCodex(Codex):
    async def exec_as_root(self, environment, command, **kwargs):
        # PilotEnvironment uploads as uid 1000, so the native auth ownership
        # and config adjustments can run as that same owner. Reject installation;
        # the exact CLI must already be in the immutable image.
        owner = environment.default_user
        if owner != '1000:1000':
            raise RuntimeError('Pilot Codex requires the fixed nonroot owner')
        auth = str(self._REMOTE_CODEX_SECRETS_DIR / 'auth.json')
        config = str(self._REMOTE_CODEX_HOME / 'config.toml')
        allowed = ([ 'chown', owner, auth ],
                   [ 'chown', owner, config, '&&', 'chmod', '600', config ])
        if shlex.split(command) not in allowed:
            raise RuntimeError('Pilot Codex does not permit runtime root installation')
        return await self.exec_as_agent(environment, command=command, **kwargs)
