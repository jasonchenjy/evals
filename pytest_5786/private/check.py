#!/usr/bin/env python3
"""Execute one private behavioral check using stdlib unittest, not candidate pytest."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(os.environ["EVAL_WORKSPACE"]) / "src"))
    spec = importlib.util.spec_from_file_location("eval_behavior", Path(__file__).parent / "tests/behavior.py")
    module = importlib.util.module_from_spec(spec)
    start = time.monotonic()
    spec.loader.exec_module(module)
    suite = unittest.TestSuite([module.Behavior(args.method)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    status = "passed"
    if result.skipped:
        status = "skipped"
    elif result.errors:
        status = "error"
    elif result.failures:
        status = "failed"
    payload = {"schema_version": 1, "method": args.method, "status": status,
               "tests_run": result.testsRun, "duration_seconds": time.monotonic() - start,
               "failures": [message for _, message in result.failures + result.errors],
               "skips": [message for _, message in result.skipped], "details": module.DETAILS}
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    return 0 if status == "passed" and result.testsRun == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
