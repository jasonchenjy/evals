"""Native Harbor config permission compatibility without granting root access."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
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


if __name__ == '__main__':
    unittest.main()
