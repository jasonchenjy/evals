"""Native Harbor Codex run/trajectory/auth; no additional root capabilities."""
import shlex
import json
from pathlib import PurePosixPath
from harbor.agents.installed.codex import Codex


def pilot_config():
    # Plugin marketplace cloning can exhaust the bounded fresh HOME even when
    # no plugin is used. This single-agent MVP uses only local coding tools.
    return {'web_search':'disabled','features':{'plugins':False,'apps':False,
        'remote_plugin':False,'skill_search':False,'skill_mcp_dependency_install':False,
        'multi_agent':False}}


class PilotCodex(Codex):
    # Native CLI refuses PATH helpers when CODEX_HOME is under /tmp.
    _REMOTE_CODEX_HOME = PurePosixPath('/home/agent/.codex')

    @staticmethod
    def check_launch(result):
        events = []
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
        errors = [e for e in events if e.get('type') in ('error', 'turn.failed') or
                  (e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'error')]
        # A shell command/test may fail legitimately; only harness launch/turn
        # errors invalidate the run. A healthy unchanged workspace remains valid.
        if result.return_code or errors or not any(e.get('type') == 'turn.completed' for e in events):
            raise RuntimeError('Codex infrastructure failure: nonzero launch, harness error, or missing completed turn; see codex.txt')

    async def exec_as_agent(self, environment, command, **kwargs):
        launch = 'codex exec ' in command
        if launch:
            environment.agent_infrastructure_ok = False
            command = 'set -o pipefail; ' + command
        result = await super().exec_as_agent(environment, command=command, **kwargs)
        if launch:
            self.check_launch(result)
            environment.agent_infrastructure_ok = True
        return result

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
