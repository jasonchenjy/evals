#!/usr/bin/env python3
"""One-task grader. Trusted local controls only; production requires an external sandbox."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prepare import BASE, snapshot


class RejectedPatch(ValueError):
    pass


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_patch(patch):
    if patch.stat().st_size > 1024 * 1024:
        raise RejectedPatch("Patch exceeds 1 MiB")
    raw = patch.read_bytes()
    if len(raw) > 1024 * 1024:
        raise RejectedPatch("Patch exceeds 1 MiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise RejectedPatch("Patch must be UTF-8") from error
    if not text.strip():
        return []
    if any(line.startswith(("GIT binary patch", "Binary files", "rename ", "copy ",
                            "old mode ", "new mode ", "similarity index")) for line in text.splitlines()):
        raise RejectedPatch("Only ordinary source-file text diffs are accepted")
    headers = [line for line in text.splitlines() if line.startswith("diff --git ")]
    if not headers:
        raise RejectedPatch("A git unified diff is required")
    allowed = set()
    for line in headers:
        match = re.fullmatch(r"diff --git a/(src/[A-Za-z0-9_./-]+\.py) b/(src/[A-Za-z0-9_./-]+\.py)", line)
        if not match or match[1] != match[2]:
            raise RejectedPatch("Disallowed patch path: " + line)
        path = match[1]
        if any(p in (".", "..", "") or p.startswith(".") for p in path.split("/")) or path == "src/_pytest/_version.py":
            raise RejectedPatch("Disallowed patch path: " + path)
        allowed.add(path)
    for line in text.splitlines():
        if line.startswith(("new file mode ", "deleted file mode ")) and not line.endswith("100644"):
            raise RejectedPatch("No executable, symlink, or other special file modes")
        if line.startswith(("--- ", "+++ ")):
            path = line[4:]
            if path == "/dev/null":
                continue
            if not path.startswith(("a/", "b/")) or path[2:] not in allowed:
                raise RejectedPatch("Noncanonical diff file header")
    # Cross-check git's own parser rather than trusting textual headers alone.
    parsed = subprocess.run(["git", "apply", "--numstat", "-z", str(patch)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if parsed.returncode:
        raise RejectedPatch("Git cannot parse submitted diff")
    actual = set()
    for entry in parsed.stdout.split(b"\0"):
        if entry:
            fields = entry.decode("utf-8").split("\t")
            if len(fields) != 3 or fields[0] == "-" or fields[1] == "-":
                raise RejectedPatch("Unsupported diff encoding")
            actual.add(fields[2])
    if actual != allowed:
        raise RejectedPatch("Patch path parser mismatch")
    return sorted(allowed)


def clean_env(workspace, scratch):
    # Explicit allowlist: no inherited credentials, Python hooks, or plugin options.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": str(scratch / "home"), "TMPDIR": str(scratch / "tmp"),
           "PYTHONPATH": str(workspace / "src"), "PYTHONHASHSEED": "0",
           "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "COLUMNS": "80",
           "TERM": "dumb", "PY_COLORS": "0", "LC_ALL": "C", "TZ": "UTC",
           "EVAL_WORKSPACE": str(workspace), "EVAL_SCRATCH": str(scratch)}
    for name in ["home", "tmp"]:
        (scratch / name).mkdir(parents=True)
    return env


def run(command, cwd, env, timeout, log):
    start = time.monotonic()
    with log.open("w") as output:
        output.write(json.dumps({"argv": command, "cwd": str(cwd)}) + "\n")
        output.flush()
        process = subprocess.Popen(command, cwd=str(cwd), env=env,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
        finally:
            # Reap any xdist/subprocess descendants that survived the direct child.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return {"command": command, "cwd": str(cwd), "returncode": code,
            "timeout": timed_out, "elapsed_seconds": time.monotonic() - start,
            "log": str(log)}


def summarize(records, catalog):
    expected = {entry["id"] for entry in catalog}
    actual = [entry["id"] for entry in records]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Missing, duplicate, or unexpected check IDs")
    definitions = {entry["id"]: entry for entry in catalog}
    dimensions = {}
    for dimension, name in [("A", "original_bug_resolution"), ("B", "cross_component_consistency"),
                            ("C", "edge_case_robustness"), ("D", "non_regression")]:
        selected = [entry for entry in records if definitions[entry["id"]]["mandatory"]
                    and dimension in definitions[entry["id"]]["dimensions"]]
        dimensions[name] = {"satisfied": bool(selected) and all(x["status"] == "passed" for x in selected),
                            "checks": {x["id"]: x["status"] for x in selected}}
    mandatory = [x for x in records if definitions[x["id"]]["mandatory"]]
    resolved = bool(mandatory) and all(x["status"] == "passed" for x in mandatory)
    return dimensions, resolved and all(x["satisfied"] for x in dimensions.values())


def grade(args):
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "eval_id": "pytest_5786", "eval_version": "0.1.0",
              "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "base_commit": BASE, "overall_resolved": False,
              "infrastructure_status": "ok", "submission_status": "pending",
              "dimensions": {}, "tests": [], "execution": [],
              "security_mode": "trusted-local-qualification-not-a-sandbox"}
    try:
        if not args.trusted_local:
            raise RuntimeError("Execution requires an external isolation facility. --trusted-local only acknowledges reviewed qualification controls; it does not create a sandbox.")
        lock = json.loads((ROOT / "checksums.json").read_text())
        result["package_lock_sha256"] = sha(ROOT / "checksums.json")
        for name, expected in lock["files"].items():
            if sha(ROOT / name) != expected:
                raise RuntimeError("Eval artifact integrity failure: " + name)
        result["patch_sha256"] = sha(args.patch)
        workspace = snapshot(args.repo, output / "workspace")
        setup = output / "setup"
        setup.mkdir()
        env = clean_env(workspace, setup)
        # Validate packages and imports on the unpatched base before evaluating code.
        preflight_code = (
            "import sys,json,pytest,pkg_resources; "
            "assert sys.version_info[:3] == (3,8,20), sys.version; "
            "reqs=[pkg_resources.Requirement.parse(x) for x in open(sys.argv[1]).read().splitlines()]; "
            "assert all(pkg_resources.get_distribution(r.project_name) in r for r in reqs); "
            "print(json.dumps({'python':sys.version,'pytest_file':pytest.__file__,"
            "'pytest_version':pytest.__version__,'packages':sorted(str(x) for x in pkg_resources.working_set)}))"
        )
        check = run([str(args.python), "-c", preflight_code, str(ROOT / "requirements.txt")],
                    workspace, env, 30, output / "preflight.log")
        result["execution"].append(check)
        if check["returncode"] or check["timeout"]:
            raise RuntimeError("Base environment preflight failed; see preflight.log")
        paths = validate_patch(args.patch)
        result["submitted_paths"] = paths
        if paths:
            for dry in [True, False]:
                command = ["git", "apply", "--whitespace=nowarn"] + (["--check"] if dry else []) + [str(args.patch)]
                applied = subprocess.run(command, cwd=str(workspace), capture_output=True, text=True)
                result["execution"].append({"command": command, "cwd": str(workspace),
                                             "returncode": applied.returncode, "stderr": applied.stderr})
                if applied.returncode:
                    raise RejectedPatch("Patch does not apply cleanly to the fixed base")
        result["submission_status"] = "accepted"
        # Curator test changes never enter the exported agent workspace.
        subprocess.run(["git", "apply", str(ROOT / "private/oracle/historical_tests.patch")],
                       cwd=str(workspace), check=True, capture_output=True)
        catalog = json.loads((ROOT / "private/test_catalog.json").read_text())
        for entry in catalog:
            scratch = output / "checks" / entry["id"]
            scratch.mkdir(parents=True)
            environment = clean_env(workspace, scratch)
            record_file = scratch / "observation.json"
            command = [str(args.python), str(ROOT / "private/check.py"),
                       "--method", entry["method"], "--output", str(record_file)]
            execution = run(command, workspace, environment, entry["timeout_seconds"], scratch / "worker.log")
            record = {"id": entry["id"], "dimensions": entry["dimensions"],
                      "mandatory": entry["mandatory"], "execution": execution}
            if execution["timeout"]:
                record["status"] = "timeout"
            elif not record_file.exists():
                record["status"] = "execution_error"
            else:
                try:
                    observed = json.loads(record_file.read_text())
                    valid = (observed["method"] == entry["method"] and observed["tests_run"] == 1
                             and observed["status"] in ["passed", "failed", "error", "skipped"])
                    if not valid:
                        raise ValueError("Invalid worker result")
                    record["observation"] = observed
                    record["status"] = observed["status"]
                    if execution["returncode"] != (0 if observed["status"] == "passed" else 1):
                        record["status"] = "execution_error"
                except (KeyError, ValueError, TypeError):
                    record["status"] = "execution_error"
            result["tests"].append(record)
        result["dimensions"], result["overall_resolved"] = summarize(result["tests"], catalog)
    except RejectedPatch as error:
        result["submission_status"] = "rejected"
        result["error"] = str(error)
    except Exception as error:
        result["infrastructure_status"] = "error"
        result["error"] = type(error).__name__ + ": " + str(error)
    finally:
        for name in ["original_bug_resolution", "cross_component_consistency", "edge_case_robustness", "non_regression"]:
            result["dimensions"].setdefault(name, {"satisfied": None, "checks": {}})
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"result": str(output / "result.json"), "overall_resolved": result["overall_resolved"],
                      "infrastructure_status": result["infrastructure_status"], "error": result.get("error")}))
    return 2 if result["infrastructure_status"] != "ok" else (0 if result["overall_resolved"] else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=lambda p: Path(p).absolute())
    parser.add_argument("--python", required=True, type=lambda p: Path(p).absolute())
    parser.add_argument("--patch", required=True, type=lambda p: Path(p).absolute())
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trusted-local", action="store_true")
    sys.exit(grade(parser.parse_args()))
