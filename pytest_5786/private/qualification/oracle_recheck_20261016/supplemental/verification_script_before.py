"""Supplemental oracle evidence; does not change the Eval's mandatory checks.

Run with the pinned Python and EVAL_WORKSPACE/EVAL_SCRATCH set by the trusted
qualification controller. Never invoke this against an unreviewed submission.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import xml.etree.ElementTree as ET

from _pytest._code.code import ExceptionInfo
from _pytest.reports import CollectReport, TestReport
from _pytest.reports import pytest_report_from_serializable, pytest_report_to_serializable

ROOT_MESSAGE = "source-side-cause-607"
FINAL_MESSAGE = "consumer-side-failure-613"
DETAILS = []
SCRATCH = Path(os.environ["EVAL_SCRATCH"])


def source(mode):
    prefix = '''class RemoteProblem(Exception):
    pass

def trigger():
'''
    if mode.startswith("missing"):
        attribute = "__cause__" if mode.endswith("explicit") else "__context__"
        return prefix + '''    error = RuntimeError(%r)
    error.%s = RemoteProblem(%r)
    raise error
''' % (FINAL_MESSAGE, attribute, ROOT_MESSAGE)
    suffix = " from cause" if mode.endswith("explicit") else ""
    return prefix + '''    try:
        raise ValueError(%r)
    except ValueError as cause:
        raise RuntimeError(%r)%s
''' % (ROOT_MESSAGE, FINAL_MESSAGE, suffix)


def info_for(mode):
    namespace = {}
    exec(compile(source(mode), "oracle_case.py", "exec"), namespace)
    try:
        namespace["trigger"]()
    except RuntimeError:
        return ExceptionInfo.from_current()
    raise AssertionError("Fixture must raise")


def markers(mode):
    cause_type = "RemoteProblem" if mode.startswith("missing") else "ValueError"
    separator = ("direct cause of the following exception" if mode.endswith("explicit")
                 else "During handling of the above exception")
    return cause_type + ": " + ROOT_MESSAGE, "RuntimeError: " + FINAL_MESSAGE, separator


CONSUMER = '''import json
import os
from pathlib import Path

def observe(report):
    if not report.failed:
        return
    value = report.longrepr
    crash = value.reprcrash
    record = {
        "worker": os.environ.get("PYTEST_XDIST_WORKER", "controller"),
        "report_type": type(report).__name__,
        "text": report.longreprtext,
        "crash_message": crash.message if crash is not None else None,
        "traceback_entries": len(value.reprtraceback.reprentries),
        "capstdout": report.capstdout,
        "none_crashes": sum(part[1] is None for part in getattr(value, "chain", [])),
    }
    Path("report_" + record["worker"] + ".json").write_text(json.dumps(record))

def pytest_runtest_logreport(report):
    observe(report)

def pytest_collectreport(report):
    observe(report)
'''


class OracleBehavior(unittest.TestCase):
    def assert_content(self, text, mode):
        first, last, separator = markers(mode)
        self.assertIn(first, text)
        self.assertIn(last, text)
        self.assertLess(text.index(first), text.index(last))
        self.assertEqual(text.count(separator), 1)

    def structured(self, mode, kind, encoding):
        representation = info_for(mode).getrepr(style="short")
        # Validate the producer fixture, not any serialized dictionary layout.
        absent = sum(part[1] is None for part in representation.chain)
        self.assertEqual(absent, 1 if mode.startswith("missing") else 0)
        common = dict(nodeid="oracle_case.py::test_failure", outcome="failed",
                      longrepr=representation, sections=[("Captured stdout call", "capture-619")])
        if kind is TestReport:
            report = kind(location=("oracle_case.py", 0, "test_failure"), keywords={},
                          when="call", duration=0.125, **common)
        else:
            report = kind(result=[], **common)
        report.longrepr.addsection("before", "section-before-631")
        before = report.longreprtext
        self.assert_content(before, mode)
        for trip in range(2):
            data = pytest_report_to_serializable(report)
            if encoding == "json":
                data = json.loads(json.dumps(data))
            report = pytest_report_from_serializable(data)
            self.assertIsInstance(report, kind)
            self.assertTrue(report.failed)
            self.assert_content(report.longreprtext, mode)
            self.assertEqual(report.longrepr.reprcrash.message, "RuntimeError: " + FINAL_MESSAGE)
            self.assertTrue(report.longrepr.reprtraceback.reprentries)
            self.assertEqual(report.capstdout, "capture-619")
            if trip == 0:
                self.assertEqual(report.longreprtext, before)
                report.longrepr.addsection("after", "section-after-641")
            else:
                self.assertIn("section-before-631", report.longreprtext)
                self.assertIn("section-after-641", report.longreprtext)
        DETAILS.append({"test": self.id(), "producer_none_crashes": absent,
                        "encoding": encoding, "round_trips": 2, "result": "passed"})

    def integration(self, mode, phase, engine):
        folder = SCRATCH / "cases" / (mode + "_" + phase + "_" + engine)
        folder.mkdir(parents=True)
        (folder / "pytest.ini").write_text("[pytest]\n")
        (folder / "conftest.py").write_text(CONSUMER)
        worker = "gw0" if engine == "xdist" else None
        code = "import os\nassert os.environ.get('PYTEST_XDIST_WORKER') == %r\n" % worker
        code += source(mode)
        code += ("\ndef test_failure():\n    print('capture-619')\n    trigger()\n"
                 if phase == "call" else "\ntrigger()\n")
        (folder / "test_case.py").write_text(code)
        command = [sys.executable, "-m", "pytest", "--color=no", "-q", "--tb=short",
                   "--junitxml=report.xml"]
        if engine == "xdist":
            command += ["-p", "xdist.plugin", "-n", "1"]
        command += ["test_case.py"]
        result = subprocess.run(command, cwd=str(folder), env=os.environ.copy(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, timeout=30)
        (folder / "output.log").write_text(result.stdout)
        DETAILS.append({"test": self.id(), "command": command, "cwd": str(folder),
                        "returncode": result.returncode, "log": str(folder / "output.log")})
        expected_exit = 2 if engine == "serial" and phase == "collect" else 1
        self.assertEqual(result.returncode, expected_exit, result.stdout[-3000:])
        self.assertNotIn("INTERNALERROR", result.stdout)
        self.assertNotIn("AttributeError", result.stdout)
        self.assert_content(result.stdout, mode)
        xml = ET.parse(str(folder / "report.xml"))
        cases = xml.findall(".//testcase")
        self.assertEqual(len(cases), 1)
        entries = cases[0].findall("failure") + cases[0].findall("error")
        self.assertEqual(len(entries), 1)
        self.assertIsNone(cases[0].find("skipped"))
        self.assert_content(entries[0].text, mode)
        remote = json.loads((folder / "report_controller.json").read_text())
        self.assertEqual(remote["report_type"], "TestReport" if phase == "call" else "CollectReport")
        self.assert_content(remote["text"], mode)
        self.assertEqual(remote["crash_message"], "RuntimeError: " + FINAL_MESSAGE)
        self.assertGreater(remote["traceback_entries"], 0)
        if phase == "call":
            self.assertEqual(remote["capstdout"], "capture-619\n")
        if engine == "xdist":
            local = json.loads((folder / "report_gw0.json").read_text())
            self.assertEqual(local["worker"], "gw0")
            self.assertEqual(local["none_crashes"], 1 if mode.startswith("missing") else 0)
            self.assertEqual(remote["text"], local["text"])


def install_cases():
    for mode in ["normal_explicit", "normal_implicit", "missing_explicit", "missing_implicit"]:
        for kind in [TestReport, CollectReport]:
            for encoding in ["hooks", "json"]:
                name = "test_structured_" + mode + "_" + kind.__name__ + "_" + encoding
                def check(self, mode=mode, kind=kind, encoding=encoding):
                    self.structured(mode, kind, encoding)
                setattr(OracleBehavior, name, check)
        for phase in ["call", "collect"]:
            for engine in ["serial", "xdist"]:
                name = "test_integration_" + mode + "_" + phase + "_" + engine
                def check(self, mode=mode, phase=phase, engine=engine):
                    self.integration(mode, phase, engine)
                setattr(OracleBehavior, name, check)


if __name__ == "__main__":
    install_cases()
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OracleBehavior))
    payload = {"schema_version": 1, "scope": "supplemental verification, not Eval scoring",
               "tests_run": result.testsRun, "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
               "failures": [{"test": t.id(), "traceback": text} for t, text in result.failures],
               "errors": [{"test": t.id(), "traceback": text} for t, text in result.errors],
               "skips": [{"test": t.id(), "reason": text} for t, text in result.skipped],
               "details": DETAILS, "elapsed_seconds": time.monotonic() - started}
    (SCRATCH / "result.json").write_text(json.dumps(payload, indent=2) + "\n")
    sys.exit(0 if result.wasSuccessful() and not result.skipped and result.testsRun == 32 else 1)
