"""Run the bounded H02 contract experiment on four reviewed source controls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "private"))
import grader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "producers").mkdir()
    (output / "sources").mkdir()
    script = ROOT / "private/qualification/probe_h02_contract.py"
    summary = {"base_commit": grader.BASE, "script_sha256": grader.sha(script),
               "scope": "trusted diagnostic probes, not scoring", "runs": [], "passed": False}
    contexts = []
    for control in ["noop", "historical", "complete", "alternative"]:
        folder = output / control
        folder.mkdir()
        workspace = grader.snapshot(args.repo.resolve(), folder / "workspace")
        patch = ROOT / "private/oracle" / (control + ".patch")
        if control != "noop":
            grader.git_apply(patch, workspace, check=True).check_returncode()
            grader.git_apply(patch, workspace).check_returncode()
        (output / "sources" / (control + "_reports.py")).write_bytes((workspace / "src/_pytest/reports.py").read_bytes())
        if control == "noop":
            for source, name in [("src/_pytest/hookspec.py", "base_hookspec.py"),
                                 ("testing/test_reports.py", "base_test_reports.py"),
                                 ("doc/en/backwards-compatibility.rst", "base_backwards_compatibility.rst"),
                                 ("src/_pytest/junitxml.py", "base_junitxml.py")]:
                (output / "sources" / name).write_bytes((workspace / source).read_bytes())
        scratch = folder / "checks"
        scratch.mkdir()
        env = grader.clean_env(workspace, scratch)
        preflight = (
            "import json,sys,pytest,pkg_resources; assert sys.version_info[:3]==(3,8,20); "
            "reqs=[pkg_resources.Requirement.parse(x) for x in open(sys.argv[1]).read().splitlines()]; "
            "assert all(pkg_resources.get_distribution(r.project_name) in r for r in reqs); "
            "print(json.dumps({'python':sys.version,'pytest_file':pytest.__file__,"
            "'packages':sorted(str(x) for x in pkg_resources.working_set)}))"
        )
        checked = grader.run([str(args.python.absolute()), "-c", preflight, str(ROOT / "requirements.txt")],
                             workspace, env, 30, folder / "preflight.log")
        if checked["returncode"] or checked["timeout"]:
            raise RuntimeError("Environment preflight failed")
        produced = grader.run([str(args.python.absolute()), str(script), "--produce",
                               str(output / "producers" / control)], workspace, env, 30, folder / "produce.log")
        summary["runs"].append({"control": control, "patch_sha256": grader.sha(patch),
                                "source_sha256": grader.sha(workspace / "src/_pytest/reports.py"),
                                "preflight": checked, "produce": produced})
        if produced["returncode"] or produced["timeout"]:
            (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            raise RuntimeError("Probe failure: " + control)
        contexts.append((workspace, env, folder))
    for row, (workspace, env, folder) in zip(summary["runs"], contexts):
        consumed = grader.run([str(args.python.absolute()), str(script), "--consume", str(output / "producers"),
                               "--output", str(folder / "cross_codec.json")], workspace, env, 30, folder / "consume.log")
        row["consume"] = consumed
    summary["passed"] = all(row["consume"]["returncode"] == 0 and not row["consume"]["timeout"]
                            for row in summary["runs"])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"passed": summary["passed"], "controls": len(summary["runs"])}))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
