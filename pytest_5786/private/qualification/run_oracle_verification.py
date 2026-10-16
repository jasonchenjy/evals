"""Run only the three reviewed oracle controls through supplemental checks."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "private"))
import grader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary = {"scope": "trusted local supplemental verification; not Eval scoring",
               "base_commit": grader.BASE, "controls": [], "qualified": False}
    script = ROOT / "private/qualification/verify_oracle_behavior.py"
    # Preserve the exact supplemental assertions along with each evidence set.
    (output / "verification_script.py").write_bytes(script.read_bytes())
    for control in ["noop", "historical", "complete"]:
        destination = output / control
        destination.mkdir()
        workspace = grader.snapshot(args.repo.resolve(), destination / "workspace")
        patch = ROOT / "private/oracle" / (control + ".patch")
        application = None
        if control != "noop":
            applied = grader.git_apply(patch, workspace)
            application = {"command": applied.args, "cwd": str(workspace),
                           "returncode": applied.returncode, "stderr": applied.stderr}
            applied.check_returncode()
        scratch = destination / "checks"
        scratch.mkdir()
        env = grader.clean_env(workspace, scratch)
        preflight = (
            "import sys,json,pytest,pkg_resources; "
            "assert sys.version_info[:3] == (3,8,20); "
            "reqs=[pkg_resources.Requirement.parse(x) for x in open(sys.argv[1]).read().splitlines()]; "
            "assert all(pkg_resources.get_distribution(r.project_name) in r for r in reqs); "
            "print(json.dumps({'python':sys.version,'pytest_file':pytest.__file__,"
            "'packages':sorted(str(x) for x in pkg_resources.working_set)}))"
        )
        checked = grader.run([str(args.python.absolute()), "-c", preflight, str(ROOT / "requirements.txt")],
                             workspace, env, 30, destination / "preflight.log")
        if checked["returncode"] or checked["timeout"]:
            raise RuntimeError("Supplemental environment preflight failed: " + control)
        execution = grader.run([str(args.python.absolute()), str(script)], workspace, env,
                               180, destination / "worker.log")
        result_file = scratch / "result.json"
        result = json.loads(result_file.read_text())
        # These exact boundaries ensure the supplemental tests can detect both
        # lost causes and the historical None regression, as well as success.
        expected_passed = {"noop": 8, "historical": 20, "complete": 32}[control]
        expected_exit = 0 if control == "complete" else 1
        row = {"control": control, "patch_sha256": grader.sha(patch),
               "applied_source_sha256": grader.sha(workspace / "src/_pytest/reports.py"),
               "script_sha256": grader.sha(script), "application": application,
               "preflight": checked, "execution": execution,
               "result_file": str(result_file), "result_sha256": grader.sha(result_file),
               "tests_run": result["tests_run"], "passed": result["passed"],
               "failures": len(result["failures"]), "errors": len(result["errors"]),
               "skips": len(result["skips"])}
        row["expectation_met"] = (row["tests_run"] == 32 and row["passed"] == expected_passed
                                  and row["skips"] == 0 and execution["returncode"] == expected_exit
                                  and not execution["timeout"])
        summary["controls"].append(row)
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(control, row["passed"], "/", row["tests_run"], row["expectation_met"], flush=True)
    summary["qualified"] = all(row["expectation_met"] for row in summary["controls"])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["qualified"] else 1


if __name__ == "__main__":
    sys.exit(main())
