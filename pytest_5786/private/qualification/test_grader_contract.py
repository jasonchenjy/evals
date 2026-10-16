"""Controller tests: reject invalid submissions and non-passing mandatory outcomes."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "private"))
import grader


class GraderContract(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "private/test_catalog.json").read_text())
        self.records = [{"id": x["id"], "status": "passed"} for x in self.catalog]

    def test_complete_and_diagnostic_policy(self):
        self.assertTrue(grader.summarize(self.records, self.catalog)[1])
        self.records[-1]["status"] = "failed"
        self.assertFalse(self.catalog[-1]["mandatory"])
        self.assertTrue(grader.summarize(self.records, self.catalog)[1])

    def test_every_nonpassing_mandatory_status_is_unresolved(self):
        for status in ["failed", "error", "skipped", "timeout", "execution_error", "unknown"]:
            with self.subTest(status=status):
                records = copy.deepcopy(self.records)
                records[0]["status"] = status
                dimensions, resolved = grader.summarize(records, self.catalog)
                self.assertFalse(resolved)
                self.assertFalse(dimensions["original_bug_resolution"]["satisfied"])

    def test_missing_duplicate_and_extra_checks(self):
        for records in [self.records[:-1], self.records + [self.records[0]],
                        self.records[:-1] + [{"id": "invented", "status": "passed"}]]:
            with self.assertRaises(ValueError):
                grader.summarize(records, self.catalog)

    def test_control_patches_are_accepted(self):
        for name in ["noop", "historical", "complete", "alternative", "last_only", "testreport_only", "text_only"]:
            result = grader.validate_patch(ROOT / "private/oracle" / (name + ".patch"))
            self.assertEqual(result, [] if name == "noop" else ["src/_pytest/reports.py"])

    def test_disallowed_patch_boundaries(self):
        complete = (ROOT / "private/oracle/complete.patch").read_text()
        bad = [complete.replace("src/_pytest/reports.py", p) for p in [
            "testing/test_reports.py", "src/../escape.py", "src/_pytest/_version.py"]]
        bad += [complete + "\nnew mode 100755\n", complete + "\nGIT binary patch\n",
                "diff --git a/src/link.py b/src/link.py\nnew file mode 120000\n"]
        with tempfile.TemporaryDirectory() as temp:
            patch = Path(temp) / "bad.patch"
            for text in bad:
                patch.write_text(text)
                with self.assertRaises(grader.RejectedPatch):
                    grader.validate_patch(patch)
            patch.write_bytes(b" " * (1024 * 1024 + 1))
            with self.assertRaises(grader.RejectedPatch):
                grader.validate_patch(patch)

    def test_timeout_is_not_a_zero_exit_success(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            result = grader.run([sys.executable, "-c", "import time; time.sleep(5)"],
                                folder, dict(os.environ), 0.1, folder / "timeout.log")
            self.assertTrue(result["timeout"])
            self.assertNotEqual(result["returncode"], 0)

    def test_patch_application_inside_enclosing_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            subprocess.run(["git", "init", "-q", str(parent)], check=True)
            (parent / ".gitignore").write_text("scratch/\n")
            workspace = parent / "scratch" / "workspace"
            (workspace / "src").mkdir(parents=True)
            source = workspace / "src" / "example.py"
            source.write_text("value = 1\n")
            patch = parent / "source.patch"
            patch.write_text("diff --git a/src/example.py b/src/example.py\n"
                             "--- a/src/example.py\n+++ b/src/example.py\n"
                             "@@ -1 +1 @@\n-value = 1\n+value = 2\n")
            # Inherited Git context must not override the clean snapshot either.
            with mock_patch.dict(os.environ, {"GIT_DIR": str(parent / ".git"),
                                               "GIT_WORK_TREE": str(parent)}):
                self.assertEqual(grader.validate_patch(patch), ["src/example.py"])
                grader.git_apply(patch, workspace, check=True).check_returncode()
                self.assertEqual(source.read_text(), "value = 1\n")
                grader.git_apply(patch, workspace).check_returncode()
            self.assertEqual(source.read_text(), "value = 2\n")
            self.assertFalse((parent / "src").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
