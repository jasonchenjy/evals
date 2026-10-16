"""Hostile handoffs use only temporary fake data; fake workers are not isolation evidence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Package, InfrastructureError, bounded
from grading import grade
from handoff import Directory, read_bytes, write_bytes, observation

ROOT = Path(__file__).resolve().parents[2]


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Package(ROOT/'pytest_5786', ROOT.parent/'pytest')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='runtime-handoff-')
        self.root = Path(self.temp.name)
        self.secret = 'FAKE_PRIVATE_MUST_NOT_CROSS_HANDOFF'
        self.victim = self.root/'controller-victim'
        self.victim.write_text(self.secret)

    def tearDown(self):
        self.temp.cleanup()

    def simulated_grade(self, attack):
        victim, secret = self.victim, self.secret
        class Worker:
            python = str(ROOT/'pytest_5786/.venv/bin/python')
            features = {}
            def canaries(self, *args, **kwargs): return {}
            def execute(self, command, cwd, env, timeout, log_prefix, read_only=()):
                log_prefix = Path(log_prefix)
                out, err = log_prefix.with_suffix('.stdout'), log_prefix.with_suffix('.stderr')
                out.write_text('normal stdout\n'); err.write_text('normal stderr\n')
                if '--output' in command:
                    obs = Path(command[command.index('--output')+1])
                    method = command[command.index('--method')+1]
                    payload = dict(schema_version=1, method=method, tests_run=1, status='passed',
                                   duration_seconds=0.01, failures=[], skips=[], details=[])
                    if attack == 'log_link':
                        # Historical worker-visible advertised path, not a forged return value.
                        (Path(env['EVAL_SCRATCH'])/'worker.log').symlink_to(victim)
                    elif attack in ('stdout_link','stderr_link'):
                        target = out if attack == 'stdout_link' else err
                        target.unlink(); target.symlink_to(victim)
                    if attack == 'observation_link': obs.symlink_to(victim)
                    elif attack == 'observation_fifo': os.mkfifo(obs)
                    elif attack == 'observation_large': obs.write_bytes(b' '*(1024*1024+1))
                    elif attack == 'observation_invalid': obs.write_text('{'+secret)
                    elif attack == 'observation_fields': obs.write_text(json.dumps({'status':'passed','details':secret}))
                    elif attack == 'observation_parent':
                        replacement = obs.parent.with_name(obs.parent.name+'-replacement')
                        obs.parent.rename(replacement)
                        malicious = replacement.parent/(replacement.name+'-fake')
                        malicious.mkdir(); (malicious/obs.name).write_text(json.dumps(dict(payload, details={'fake':secret})))
                        obs.parent.symlink_to(malicious, target_is_directory=True)
                    else: obs.write_text(json.dumps(payload))
                return dict(stdout=str(out), stderr=str(err), returncode=0, timeout=False)
        result = grade(self.package, Worker(), ROOT/'pytest_5786/private/oracle/noop.patch', self.root/'grading', {})
        self.assertEqual(self.victim.read_text(), secret)
        self.assertNotIn(secret, json.dumps(result))
        for p in (self.root/'grading').rglob('*'):
            if p.is_file() and not p.is_symlink() and p.suffix in ('.log','.stdout','.stderr'):
                self.assertNotIn(secret, p.read_text())
        return result

    def test_merged_log_link_does_not_overwrite_controller(self):
        # After relocation this worker-owned decoy is never read or overwritten.
        result = self.simulated_grade('log_link')
        self.assertEqual(result['infrastructure_status'], 'ok')
        self.assertTrue(result['overall_resolved'])

    def test_capture_links_rejected_without_disclosure(self):
        for attack in ('stdout_link','stderr_link'):
            with self.subTest(attack=attack):
                result = self.simulated_grade(attack)
                self.assertEqual(result['infrastructure_status'], 'error')
                # Next iteration needs a separate pristine output tree.
                self.tearDown(); self.setUp()

    def test_observation_rejects_unsafe_or_invalid_outputs(self):
        for attack in ('observation_link','observation_fifo','observation_large',
                       'observation_invalid','observation_fields','observation_parent'):
            with self.subTest(attack=attack):
                start = time.monotonic()
                result = self.simulated_grade(attack)
                self.assertEqual(result['infrastructure_status'], 'error')
                self.assertLess(time.monotonic()-start, 10)
                self.tearDown(); self.setUp()

    def test_normal_logs_and_observation(self):
        result = self.simulated_grade('normal')
        self.assertEqual(result['infrastructure_status'], 'ok')
        self.assertTrue(result['overall_resolved'])
        self.assertEqual(len(result['tests']), 13)

    def test_bounded_rejects_preplaced_capture_and_record_links(self):
        for suffix in ('.stdout','.stderr','.execution.json'):
            with self.subTest(suffix=suffix):
                prefix = self.root/('capture'+suffix.replace('.','-'))
                prefix.with_suffix(suffix).symlink_to(self.victim)
                with self.assertRaises(InfrastructureError):
                    bounded([sys.executable,'-c','print("normal")'], self.root,
                            {'PATH':'/usr/bin:/bin'}, 2, prefix)
                self.assertEqual(self.victim.read_text(), self.secret)

    def test_parent_links_and_hardlinks_are_rejected(self):
        linked = self.root/'linked'
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(InfrastructureError): read_bytes(linked/'controller-victim')
        with self.assertRaises(InfrastructureError): write_bytes(linked/'controller-victim', b'overwrite')
        hard = self.root/'hard'
        os.link(self.victim, hard)
        with self.assertRaises(InfrastructureError): read_bytes(hard)
        with self.assertRaises(InfrastructureError): write_bytes(hard, b'overwrite')
        self.assertEqual(self.victim.read_text(), self.secret)

    def test_replacement_between_open_and_read_is_rejected(self):
        regular = self.root/'regular'
        regular.write_bytes(b'public')
        real_read = os.read
        replaced = False
        def swap(fd, size):
            nonlocal replaced
            if not replaced:
                replaced = True
                regular.unlink(); regular.symlink_to(self.victim)
            return real_read(fd, size)
        with mock.patch('handoff.os.read', side_effect=swap):
            with self.assertRaises(InfrastructureError): read_bytes(regular)
        self.assertEqual(self.victim.read_text(), self.secret)

    def test_late_destination_link_is_replaced_without_following(self):
        target = self.root/'destination'
        real_replace = os.replace
        def swap(src, dst, **kwargs):
            target.symlink_to(self.victim)
            return real_replace(src, dst, **kwargs)
        with mock.patch('handoff.os.replace', side_effect=swap):
            write_bytes(target, b'public')
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_bytes(), b'public')
        self.assertEqual(self.victim.read_text(), self.secret)

    def test_capture_replacement_after_launch_is_rejected(self):
        prefix = self.root/'live'
        program = ("from pathlib import Path; p=Path("+repr(str(prefix.with_suffix('.stdout')))+
                   ");p.unlink();p.symlink_to("+repr(str(self.victim))+");print('public')")
        with self.assertRaises(InfrastructureError):
            bounded([sys.executable,'-c',program], self.root, {'PATH':'/usr/bin:/bin'}, 2, prefix)
        self.assertEqual(self.victim.read_text(), self.secret)
        self.assertNotIn(self.secret, prefix.with_suffix('.execution.json').read_text())

    def test_invalid_observation_types_and_duplicates(self):
        base = dict(schema_version=1, method='test_public', tests_run=1, status='passed',
                    duration_seconds=0.01, failures=[], skips=[], details=[])
        for key, value in [('tests_run',True),('duration_seconds',float('nan')),
                           ('details',{}),('failures','text'),('method','wrong')]:
            with self.subTest(key=key), self.assertRaises(InfrastructureError):
                observation(json.dumps(dict(base, **{key:value})).encode(), 'test_public')
        with self.assertRaises(InfrastructureError):
            observation(b'{"status":"failed","status":"passed"}', 'test_public')

    def test_native_launcher_rejects_capture_in_writable_ancestor(self):
        from sandbox import NativeSandbox
        sandbox = object.__new__(NativeSandbox)
        sandbox.controller = self.root/'controller'
        workspace = self.root/'work'; workspace.mkdir()
        scratch = self.root/'scratch'; scratch.mkdir()
        with self.assertRaises(InfrastructureError):
            sandbox.execute([], workspace, {'EVAL_SCRATCH':str(scratch)}, 1, workspace/'logs/worker')

    def test_group_writable_capture_parent_rejected(self):
        folder = self.root/'mutable'; folder.mkdir(); folder.chmod(0o777)
        with self.assertRaises(InfrastructureError): write_bytes(folder/'log', b'public')


if __name__ == '__main__': unittest.main(verbosity=2)
