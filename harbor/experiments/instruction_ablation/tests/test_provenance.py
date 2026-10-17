import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import experiment as e


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=e.common.load_runtime()[0](e.REPO/'pytest_5786',e.REPO.parent/'pytest')

    def test_b_and_c_pass_full_frozen_validation(self):
        for variant in ('B','C'):
            self.assertEqual(e.validate_task(e.HERE/'generated'/variant,self.package)['experiment_variant'],variant)

    def test_task_tampering_is_rejected(self):
        original=e.common.task_hashes
        def altered(path):
            result=original(path)
            if Path(path).resolve()==(e.HERE/'generated/B').resolve():result['instruction.md']='0'*64
            return result
        with patch.object(e.common,'task_hashes',side_effect=altered):
            with self.assertRaisesRegex(AssertionError,'Variant task changed'):
                e.validate_task(e.HERE/'generated/B',self.package)

    def test_experiment_code_change_is_rejected(self):
        with patch.object(e,'experiment_hashes',return_value={}):
            with self.assertRaisesRegex(AssertionError,'Experiment code changed'):e.load_lock()

    def test_unrecognized_task_is_rejected(self):
        with self.assertRaisesRegex(AssertionError,'Only the two frozen'):
            e.validate_task(e.TEMPLATE,self.package)

    def test_original_eval_identity_is_still_checked(self):
        with patch.object(e,'ORIGINAL_VALIDATE',side_effect=RuntimeError('original integrity gate')):
            with self.assertRaisesRegex(RuntimeError,'original integrity gate'):
                e.validate_task(e.HERE/'generated/B',self.package)

    def test_live_requires_explicit_flags_and_auth_selection(self):
        args=SimpleNamespace(mode='live',variant='B',output=e.HERE/'raw/unexecuted-test',
            auth_file=None,approve_container_credentials=False,approve_public_network=False)
        with self.assertRaisesRegex(ValueError,'fresh human approval'):asyncio.run(e.main(args))
        self.assertFalse(args.output.exists())


if __name__=='__main__':unittest.main(verbosity=2)
