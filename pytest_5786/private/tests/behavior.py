"""Independent unittest driver; assertions target report consumption, not wire keys."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

from _pytest._code.code import ExceptionInfo
from _pytest.reports import CollectReport, TestReport
from _pytest.reports import pytest_report_from_serializable, pytest_report_to_serializable

WORKSPACE = Path(os.environ["EVAL_WORKSPACE"])
SCRATCH = Path(os.environ["EVAL_SCRATCH"])
DETAILS = []


def non_output_elements(case):
    return [x for x in case if x.tag not in ("system-out", "system-err", "properties")]


def exception_info(mode="explicit", depth=2):
    def raise_level(level):
        if level == 0:
            raise ValueError("layer-0")
        try:
            raise_level(level - 1)
        except ValueError as cause:
            if mode == "explicit":
                raise ValueError("layer-%d" % level) from cause
            if mode == "suppressed":
                raise ValueError("layer-%d" % level) from None
            raise ValueError("layer-%d" % level)
    try:
        raise_level(depth - 1)
    except ValueError:
        return ExceptionInfo.from_current()


def remote_info():
    class RemoteCause(Exception):
        def __str__(self):
            return "remote-message-713"
    try:
        error = ValueError("outer-message-829")
        error.__cause__ = RemoteCause()
        raise error
    except ValueError:
        return ExceptionInfo.from_current()


def report(info=None, kind=TestReport, outcome="failed", longrepr=None):
    value = info.getrepr(style="short") if info is not None else longrepr
    common = dict(nodeid="sample.py::test_case", outcome=outcome, longrepr=value,
                  sections=[("Captured stdout call", "captured-419"),
                            ("Captured stderr call", "stderr-421")])
    if kind is TestReport:
        return kind(location=("sample.py", 7, "test_case"), keywords={"tag": 1},
                    when="call", duration=0.25, **common)
    return kind(result=[], **common)


def transport(rep):
    # Hooks and JSON are the interoperability contract; no key layout is asserted.
    data = json.loads(json.dumps(pytest_report_to_serializable(rep)))
    return pytest_report_from_serializable(data)


def run_pytest(folder, args, label):
    command = [sys.executable, "-m", "pytest", "--color=no", "-q"] + args
    result = subprocess.run(command, cwd=str(folder), env=os.environ.copy(),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True, timeout=45)
    log = SCRATCH / (label + ".log")
    log.write_text(result.stdout)
    DETAILS.append({"command": command, "cwd": str(folder),
                    "returncode": result.returncode, "log": str(log)})
    return result


class Behavior(unittest.TestCase):
    def assert_chain(self, rep, depth, description):
        text = rep.longreprtext
        markers = ["ValueError: layer-%d" % i for i in range(depth)]
        for marker in markers:
            self.assertIn(marker, text)
        positions = [text.index(x) for x in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(text.count(description), depth - 1)
        self.assertTrue(rep.failed)

    def test_A01_explicit(self):
        for rep in [report(exception_info()), transport(report(exception_info()))]:
            self.assert_chain(rep, 2, "direct cause of the following exception")

    def test_A02_implicit(self):
        original = report(exception_info("implicit", 3))
        self.assert_chain(original, 3, "During handling of the above exception")
        self.assert_chain(transport(original), 3, "During handling of the above exception")

    def test_B01_collect_report(self):
        original = report(exception_info(), CollectReport)
        original.longrepr.addsection("collector-detail", "payload-443", "=")
        restored = transport(original)
        self.assertIsInstance(restored, CollectReport)
        self.assert_chain(restored, 2, "direct cause of the following exception")
        self.assertIn("payload-443", restored.longreprtext)
        self.assertEqual(restored.capstdout, "captured-419")

    def test_B02_structured_consumer(self):
        original = report(exception_info())
        original.longrepr.addsection("before-transport", "section-457", "=")
        restored = transport(original)
        # Existing JUnit/report consumers use reprcrash.message, and existing
        # traceback consumers use reprtraceback. A string-only workaround fails.
        self.assertEqual(restored.longrepr.reprcrash.message, "ValueError: layer-1")
        self.assertGreater(restored.longrepr.reprcrash.lineno, 0)
        self.assertTrue(restored.longrepr.reprtraceback.reprentries)
        self.assertEqual(restored.longrepr.reprcrash.path, original.longrepr.reprcrash.path)
        self.assertEqual(restored.when, "call")
        self.assertEqual(restored.duration, 0.25)
        self.assertEqual(restored.keywords, {"tag": 1})
        self.assertEqual(restored.capstdout, "captured-419")
        self.assertEqual(restored.capstderr, "stderr-421")
        restored.longrepr.addsection("after-transport", "section-461")
        again = transport(restored)
        for value in ["section-457", "section-461"]:
            self.assertIn(value, again.longreprtext)
        self.assert_chain(again, 2, "direct cause of the following exception")

    def test_B03_real_xdist(self):
        code = '''import os
assert os.environ.get("PYTEST_XDIST_WORKER") == "gw0"
def fail():
    try:
        raise ValueError("worker-inner-503")
    except ValueError as e:
        raise RuntimeError("worker-outer-509") from e
'''
        for mode in ["call", "collect"]:
            folder = SCRATCH / mode
            folder.mkdir()
            (folder / "pytest.ini").write_text("[pytest]\n")
            (folder / "test_transport.py").write_text(code + (
                "\ndef test_remote():\n    fail()\n" if mode == "call" else "\nfail()\n"))
            result = run_pytest(folder, ["-p", "xdist.plugin", "-n", "1", "--tb=short",
                                         "--junitxml=report.xml", "test_transport.py"], mode)
            self.assertEqual(result.returncode, 1)
            if mode == "call":
                self.assertIn("[gw0]", result.stdout)
            self.assertNotIn("INTERNALERROR", result.stdout)
            self.assertIn("ValueError: worker-inner-503", result.stdout)
            self.assertIn("RuntimeError: worker-outer-509", result.stdout)
            self.assertIn("direct cause", result.stdout)
            xml = ET.parse(str(folder / "report.xml"))
            entries = xml.findall(".//testcase/failure") + xml.findall(".//testcase/error")
            self.assertEqual(len(entries), 1)
            self.assertIn("worker-inner-503", entries[0].text)
            self.assertIn("worker-outer-509", entries[0].text)

    def test_C01_suppressed_context(self):
        original = report(exception_info("suppressed", 3))
        restored = transport(original)
        for rep in [original, restored]:
            self.assertIn("ValueError: layer-2", rep.longreprtext)
            self.assertNotIn("ValueError: layer-0", rep.longreprtext)
            self.assertNotIn("ValueError: layer-1", rep.longreprtext)
            self.assertNotIn("During handling of", rep.longreprtext)
            self.assertNotIn("direct cause of", rep.longreprtext)

    def test_C02_long_chain_and_render_option(self):
        for kind in [TestReport, CollectReport]:
            info = exception_info("explicit", 4)
            self.assert_chain(transport(report(info, kind)), 4,
                              "direct cause of the following exception")
            local = report(kind=kind, longrepr=info.getrepr(style="short", chain=False))
            restored = transport(local)
            self.assertIn("ValueError: layer-3", restored.longreprtext)
            self.assertNotIn("ValueError: layer-0", restored.longreprtext)

    def test_C03_missing_traceback(self):
        for kind in [TestReport, CollectReport]:
            original = report(remote_info(), kind)
            # The historical producer already accepts a cause without __traceback__.
            self.assertIn("RemoteCause: remote-message-713", original.longreprtext)
            restored = transport(original)
            self.assertIn("RemoteCause: remote-message-713", restored.longreprtext)
            self.assertIn("ValueError: outer-message-829", restored.longreprtext)
            self.assertIn("direct cause of", restored.longreprtext)
            self.assertTrue(restored.failed)
            self.assertEqual(restored.longrepr.reprcrash.message, "ValueError: outer-message-829")

    def test_D01_ordinary_reports(self):
        for outcome, value in [("passed", None), ("skipped", ("sample.py", 8, "reason-521")),
                               ("failed", "custom-message-523")]:
            for kind in [TestReport, CollectReport]:
                original = report(kind=kind, outcome=outcome, longrepr=value)
                restored = transport(original)
                self.assertEqual(restored.outcome, outcome)
                self.assertEqual(restored.nodeid, original.nodeid)
                self.assertEqual(restored.capstdout, original.capstdout)
                if isinstance(value, tuple):
                    self.assertEqual(list(restored.longrepr), list(value))
                else:
                    self.assertEqual(restored.longrepr, value)
        original = report(exception_info(depth=1))
        from _pytest.pathlib import Path as ReportPath
        original.extra_path = ReportPath("extra-report-path")
        original.extra_flag = True
        restored = transport(original)
        self.assertEqual(restored.longreprtext, original.longreprtext)
        self.assertEqual(restored.longrepr.reprcrash.message, "ValueError: layer-0")
        self.assertEqual(restored.extra_path, "extra-report-path")
        self.assertIs(restored.extra_flag, True)

    def test_D02_existing_behavior(self):
        output = SCRATCH / "existing.xml"
        result = run_pytest(WORKSPACE, ["--tb=short", "--junitxml=" + str(output),
            "testing/test_reports.py", "testing/code/test_code.py", "testing/code/test_excinfo.py",
            "-k", "not test_chained_exceptions and not test_xdist_longrepr_to_str_issue_241 and not test_deserialization_failure and not test_paths_support and not TestHooks"], "existing")
        self.assertEqual(result.returncode, 0, result.stdout[-4000:])
        cases = ET.parse(str(output)).findall(".//testcase")
        self.assertEqual(len(cases), 118)
        actual = sorted((x.attrib.get("classname", ""), x.attrib["name"]) for x in cases)
        expected = json.loads((Path(__file__).parent / "existing_inventory.json").read_text())
        self.assertEqual([list(x) for x in actual], expected)
        for case in cases:
            self.assertEqual(non_output_elements(case), [], ET.tostring(case).decode())
        DETAILS.append({"existing_tests": 118, "passed": 118, "skipped": 0})

    def test_D03_missing_traceback_no_new_crash(self):
        # Separate from C03: the base already survives this input but loses its
        # cause. D measures no NEW crash; C measures the restored cause content.
        for kind in [TestReport, CollectReport]:
            restored = transport(report(remote_info(), kind))
            self.assertTrue(restored.failed)
            self.assertIn("ValueError: outer-message-829", restored.longreprtext)

    def test_H01_historical_focused(self):
        output = SCRATCH / "historical.xml"
        result = run_pytest(WORKSPACE, ["--tb=short", "--junitxml=" + str(output),
            "testing/test_reports.py::TestReportSerialization::test_chained_exceptions"], "historical")
        cases = ET.parse(str(output)).findall(".//testcase")
        DETAILS.append({"historical_cases": len(cases),
                        "passed": sum(not non_output_elements(x) for x in cases),
                        "failures": sum(x.find("failure") is not None for x in cases),
                        "skips": sum(x.find("skipped") is not None for x in cases)})
        self.assertEqual(result.returncode, 0, result.stdout[-4000:])
        self.assertEqual(len(cases), 2)
        for case in cases:
            self.assertEqual(non_output_elements(case), [])

    def test_H02_full_existing_suite(self):
        output = SCRATCH / "full-existing.xml"
        result = run_pytest(WORKSPACE, ["--tb=short", "--junitxml=" + str(output),
            "testing/test_reports.py", "testing/code/test_code.py", "testing/code/test_excinfo.py",
            "-k", "not test_chained_exceptions"], "full-existing")
        cases = ET.parse(str(output)).findall(".//testcase")
        DETAILS.append({"existing_tests": len(cases),
                        "passed": sum(not non_output_elements(x) for x in cases),
                        "skipped": sum(x.find("skipped") is not None for x in cases)})
        self.assertEqual(result.returncode, 0, result.stdout[-4000:])
        self.assertEqual(len(cases), 125)
        for case in cases:
            self.assertEqual(non_output_elements(case), [])
