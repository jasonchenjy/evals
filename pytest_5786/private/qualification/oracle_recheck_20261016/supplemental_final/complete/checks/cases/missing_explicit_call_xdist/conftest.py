import json
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
        "representation_text": str(value),
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
