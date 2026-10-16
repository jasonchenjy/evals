"""Deterministic controller tests; no model calls or untrusted host execution."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Package, bounded, git
from submission import collect, assert_applied
import agent
from grading import grade
from core import InfrastructureError

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT/'pytest_5786'
REPO = ROOT.parent/'pytest'


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Package(EVAL, REPO)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pytest5786-runtime-test-')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, name='work'):
        work = self.root/name
        baseline = self.package.prepare(work)
        return work, baseline

    def test_A_exact_restoration(self):
        work, baseline = self.export()
        self.assertFalse(git(work,'status','--porcelain'))
        self.assertEqual(git(work,'rev-list','--all','--count').strip(), b'1')
        self.assertFalse(git(work,'remote'))
        self.assertFalse((work/'private').exists())
        self.assertFalse((work/'.git/objects/info/alternates').exists())
        with self.assertRaises(subprocess.CalledProcessError):
            git(work,'cat-file','-t',self.package.task['repository']['base_commit'])
        self.assertEqual(len(baseline),40)

    def test_C_patch_bytes_untracked_delete_dirty_git_and_reset(self):
        work, baseline = self.export()
        changed = 'src/_pytest/reports.py'
        (work/changed).write_text((work/changed).read_text()+'\n# harmless probe\n')
        (work/'src/_pytest/probe_new.py').write_text('# new source only\n')
        (work/'src/_pytest/_argcomplete.py').unlink()
        (work/'test_debug.py').write_text('assert True\n')
        (work/'testing/test_reports.py').write_text('# an out-of-scope existing test edit\n')
        # Candidate Git and attributes are intentionally unusable/untrusted.
        (work/'.git/HEAD').write_text('ref: refs/heads/not-the-baseline\n')
        (work/'.git/config').write_text('[filter "evil"]\nclean = false\n')
        (work/'.gitattributes').write_text('*.py filter=evil\n')
        result = collect(self.package, work, baseline, self.root/'submission')
        self.assertEqual(result['changed_files'], sorted(['src/_pytest/_argcomplete.py',changed,'src/_pytest/probe_new.py']))
        self.assertIn('test_debug.py',result['excluded_files'])
        self.assertIn('.gitattributes',result['excluded_files'])
        self.assertIn('testing/test_reports.py',result['excluded_files'])
        target, _ = self.export('target')
        old = dict(os.environ)
        try:
            os.environ['GIT_DIR']=str(work/'.git')
            os.environ['GIT_WORK_TREE']=str(work)
            applied = assert_applied(self.package, result['patch'], target, result['source_sha256'])
        finally:
            os.environ.clear(); os.environ.update(old)
        self.assertEqual(applied,result['source_sha256'])
        self.assertEqual((target/changed).read_bytes(), (work/changed).read_bytes())
        fresh, fresh_sha = self.export('fresh')
        self.assertEqual(fresh_sha,baseline)
        self.assertFalse((fresh/'src/_pytest/probe_new.py').exists())
        self.assertFalse((fresh/'test_debug.py').exists())

    def test_C_noop(self):
        work, baseline = self.export()
        result=collect(self.package,work,baseline,self.root/'submission')
        self.assertEqual(Path(result['patch']).read_bytes(), b'')
        self.assertEqual(result['changed_files'], [])
        target, _ = self.export('target')
        self.assertEqual(assert_applied(self.package,result['patch'],target,{}),{})

    def test_C_reject_symlink_and_mode_and_shim(self):
        for kind in ['symlink','mode','shim','fifo']:
            work,baseline=self.export(kind)
            if kind=='symlink': (work/'src/_pytest/probe.py').symlink_to('/dev/null')
            elif kind=='fifo': os.mkfifo(work/'src/_pytest/probe.py')
            elif kind=='mode': (work/'src/_pytest/reports.py').chmod(0o755)
            else: (work/'src/_pytest/_version.py').write_text('version="fake"\n')
            with self.subTest(kind=kind), self.assertRaises(self.package.grader.RejectedPatch):
                collect(self.package,work,baseline,self.root/(kind+'-patch'))

    def test_F_bounded_timeout_and_output_cap(self):
        # Only our deterministic sleep child; no candidate code on the controller.
        script="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time;time.sleep(8)']); print('started',flush=True);time.sleep(8)"
        result=bounded([sys.executable,'-c',script],self.root,{'PATH':'/usr/bin:/bin'},.3,self.root/'timeout')
        self.assertTrue(result['timeout'])
        self.assertEqual(result['returncode'],-9)
        self.assertLess(result['elapsed_seconds'],3)
        self.assertNotIn('descendant_pipe_leak',result)
        result=bounded([sys.executable,'-c',"import sys,time;sys.stdout.write('x'*20000);sys.stdout.flush();time.sleep(8)"],self.root,{'PATH':'/usr/bin:/bin'},5,self.root/'capped',output_limit=4096)
        self.assertTrue(result['output_limit_exceeded'])
        self.assertLessEqual(Path(result['stdout']).stat().st_size+Path(result['stderr']).stat().st_size,4096)

    def test_F_fresh_argv_model_and_public_prompt(self):
        class Fake:
            codex='/codex'
            python='/deps/python'
            def permissions(self,*args): return '{}'
        work,_=self.export()
        command=agent.build_command(Fake(),work,self.root/'scratch','chosen-model',self.root/'final.txt')
        self.assertNotIn('resume',command); self.assertNotIn('fork',command)
        self.assertEqual(command[command.index('--model')+1],'chosen-model')
        self.assertIn('--ephemeral',command); self.assertIn('--ignore-user-config',command)
        self.assertIn('--json',command); self.assertIn('--no-daemon',command)
        text=agent.prompt(work,Fake.python)
        self.assertTrue(text.startswith((work/'TASK.md').read_text()))
        self.assertNotIn('complete.patch',text)

    def test_F_closed_pipes_do_not_mean_process_finished(self):
        target=self.root/'finished'
        code="import os,time;from pathlib import Path;os.close(1);os.close(2);time.sleep(.15);Path('finished').write_text('done')"
        result=bounded([sys.executable,'-c',code],self.root,{'PATH':'/usr/bin:/bin'},2,self.root/'closed-pipes')
        self.assertEqual(result['returncode'],0)
        self.assertEqual(target.read_text(),'done')
        self.assertNotIn('cleanup_error',result)

    def test_F_capture_fake_cli_transport_is_not_model_evidence(self):
        script=self.root/'fake_cli.py'
        script.write_text("import sys,pathlib,json; p=sys.stdin.read(); pathlib.Path(sys.argv[1]).write_text('fake final');print(json.dumps({'type':'fixture.event','prompt_received':p}))")
        result=bounded([sys.executable,str(script),str(self.root/'final')],self.root,{'PATH':'/usr/bin:/bin'},3,self.root/'fake-events',input_text='public prompt')
        self.assertEqual(result['returncode'],0)
        self.assertEqual(json.loads(Path(result['stdout']).read_text())['prompt_received'],'public prompt')
        self.assertEqual((self.root/'final').read_text(),'fake final')

    def test_E_worker_startup_error_is_infrastructure_and_adapter_restores(self):
        class FailedWorker:
            python = str(EVAL/'.venv/bin/python')
            features = {}
            def canaries(self,*args,**kwargs): return {}  # unit stub, not isolation evidence
            def execute(self,*args,**kwargs): raise InfrastructureError('test worker startup failure')
        original = self.package.grader.run
        result = grade(self.package, FailedWorker(), EVAL/'private/oracle/noop.patch',self.root/'grading',{})
        self.assertEqual(result['infrastructure_status'],'error')
        self.assertEqual(result['tests'],[])
        self.assertIn('test worker startup failure',result['error'])
        self.assertIs(self.package.grader.run,original)

    def test_F_credentials_home_cannot_be_inside_workspace(self):
        class Boundary:
            readable=[]
        work,_=self.export()
        with self.assertRaises(InfrastructureError):
            agent.inspect(Boundary(),work,self.root/'audit',controller_home=work/'client')
        self.assertFalse((work/'client/.codex').exists())


if __name__=='__main__': unittest.main(verbosity=2)
