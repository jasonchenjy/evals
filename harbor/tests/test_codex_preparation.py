"""Native Harbor config permission compatibility without granting root access."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import json
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pilot'))
from codex_agent import PilotCodex


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent = PilotCodex(logs_dir=Path(self.temp.name), model_name='openai/gpt-6.1-sol')
        self.agent.exec_as_agent = AsyncMock()
        self.env = SimpleNamespace(default_user='1000:1000', upload_file=AsyncMock())

    async def test_native_config_upload_uses_nonroot(self):
        path = str(self.agent._REMOTE_CODEX_HOME / 'config.toml')
        await self.agent._upload_config_text(self.env, content='web_search = "disabled"\n',
                                            remote_path=path, filename='config.toml')
        self.env.upload_file.assert_awaited_once()
        self.agent.exec_as_agent.assert_awaited_once_with(
            self.env, command=f'chown 1000:1000 {path} && chmod 600 {path}')

    async def test_auth_ownership_uses_nonroot(self):
        command = f'chown 1000:1000 {self.agent._REMOTE_CODEX_SECRETS_DIR / "auth.json"}'
        await self.agent.exec_as_root(self.env, command)
        self.agent.exec_as_agent.assert_awaited_once_with(self.env, command=command)

    async def test_other_root_commands_rejected(self):
        config = str(self.agent._REMOTE_CODEX_HOME / 'config.toml')
        for command in ['apt-get update', 'chown 1000:1000 /etc/passwd',
                        f'chown 1000:1000 {config} && chmod 777 {config}',
                        f'chown 1000:1000 {config} && chmod 600 {config}; id',
                        f'chown 1000:1000 {config} && chmod 600 /etc/passwd']:
            with self.subTest(command=command), self.assertRaises(RuntimeError):
                await self.agent.exec_as_root(self.env, command)
        self.agent.exec_as_agent.assert_not_awaited()

    async def test_root_default_user_rejected(self):
        self.env.default_user = 'root'
        with self.assertRaises(RuntimeError):
            await self.agent.exec_as_root(self.env, 'chown root /tmp/auth.json')
        self.agent.exec_as_agent.assert_not_awaited()

    def test_harness_failure_is_not_a_valid_empty_submission(self):
        log='\n'.join(json.dumps(x) for x in [
            {'type':'item.completed','item':{'type':'error','message':'Code Mode is unavailable'}},
            {'type':'turn.completed'}])
        with self.assertRaisesRegex(RuntimeError,'infrastructure failure'):
            PilotCodex.check_launch(SimpleNamespace(return_code=0,stdout=log))

    def test_shell_failure_and_healthy_noop_are_valid(self):
        for events in [[{'type':'turn.completed'}],
                       [{'type':'item.completed','item':{'type':'command_execution','exit_code':7,'status':'failed'}},
                        {'type':'turn.completed'}]]:
            PilotCodex.check_launch(SimpleNamespace(return_code=0,stdout='\n'.join(map(json.dumps,events))))

    def test_incomplete_or_nonzero_launch_rejected(self):
        for code,log in [(0,''),(1,'{"type":"turn.completed"}'),(0,'{"type":"turn.failed"}')]:
            with self.assertRaises(RuntimeError):
                PilotCodex.check_launch(SimpleNamespace(return_code=code,stdout=log))


if __name__ == '__main__':
    unittest.main()
