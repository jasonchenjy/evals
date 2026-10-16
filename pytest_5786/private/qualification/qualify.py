#!/usr/bin/env python3
"""Fixed deterministic controls for this task only. Never invokes a coding agent."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CONTROLS = ["noop", "historical", "complete", "alternative", "last_only", "testreport_only", "text_only"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    summary = {"schema_version": 1, "eval_version": "0.1.0", "controls": [],
               "agent_trials_run": False, "scope": "trusted local deterministic qualification"}
    for control in CONTROLS:
        command = [sys.executable, str(ROOT / "private/grader.py"), "--repo", str(args.repo.absolute()),
                   "--python", str(args.python.absolute()), "--patch", str(ROOT / "private/oracle" / (control + ".patch")),
                   "--output", str(output / control), "--trusted-local"]
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (output / (control + ".invocation.log")).write_text(json.dumps(command) + "\n" + process.stdout)
        path = output / control / "result.json"
        result = json.loads(path.read_text())
        entry = {"control": control, "command": command, "returncode": process.returncode,
                 "result_file": str(path), "result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "infrastructure_status": result["infrastructure_status"],
                 "overall_resolved": result["overall_resolved"], "dimensions": result["dimensions"],
                 "checks": {x["id"]: x["status"] for x in result["tests"]}}
        entry["expected_overall"] = control in ("complete", "alternative")
        entry["expectation_met"] = (entry["overall_resolved"] == entry["expected_overall"] and
                                    entry["infrastructure_status"] == "ok")
        summary["controls"].append(entry)
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(control, process.returncode, entry["overall_resolved"], entry["checks"], flush=True)
    by_name = {x["control"]: x for x in summary["controls"]}
    # Check the specific expected capability boundaries, not just a negative score.
    boundaries = {
        "noop_original_fails": by_name["noop"]["checks"].get("A01") == "failed",
        "noop_unaffected_passes": all(by_name["noop"]["checks"].get(x) == "passed" for x in ["D01", "D02"]),
        "historical_original_passes": by_name["historical"]["dimensions"]["original_bug_resolution"]["satisfied"] is True,
        "historical_focused_passes": by_name["historical"]["checks"].get("H01") == "passed",
        "historical_missing_traceback_exposed": by_name["historical"]["checks"].get("C03") == "error",
        "last_only_rejected": by_name["last_only"]["checks"].get("A01") == "failed",
        "test_only_collect_rejected": by_name["testreport_only"]["checks"].get("B01") == "failed",
        "text_only_structure_rejected": by_name["text_only"]["checks"].get("B02") == "error",
    }
    summary["boundary_checks"] = boundaries
    summary["qualification_passed"] = all(x["expectation_met"] for x in summary["controls"]) and all(boundaries.values())
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["qualification_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
