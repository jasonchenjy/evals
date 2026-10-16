#!/usr/bin/env python3
"""Export only the allowlisted agent payload. No model or runtime integration."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
BASE = "955e54221008aba577ecbaefa15679f6777d3bf8"
VERSION = "# Eval packaging shim; source identity is defined by the base commit.\nversion = '5.1.0'\n"


def snapshot(repo, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    data = subprocess.check_output(["git", "-C", str(repo), "archive", BASE])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts or member.issym() or member.islnk():
                raise ValueError("Unsafe base archive member: " + member.name)
        archive.extractall(str(destination))
    # Confirm tracked bytes before the one documented generated-file addition.
    expected = json.loads((ROOT / "base_files.json").read_text())
    for name, sha in expected.items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != sha:
            raise ValueError("Base identity mismatch: " + name)
    (destination / "src/_pytest/_version.py").write_text(VERSION)
    return destination


def export(repo, destination):
    dest = snapshot(repo, destination)
    shutil.copyfile(ROOT / "instruction.md", dest / "TASK.md")
    shutil.copytree(ROOT / "tests/public", dest / "eval_public")
    shutil.copyfile(ROOT / "requirements.txt", dest / "eval_requirements.txt")
    public = {
        "eval_id": "pytest_5786", "eval_version": "0.1.0",
        "capability": "Cross-Component Reasoning & Bug Fixing",
        "base_commit": BASE, "instruction": "TASK.md",
        "public_examples": "eval_public", "python": "3.8.20",
        "patch_paths": "src/**/*.py except src/_pytest/_version.py",
        "defaults": {"wall_seconds": 1800, "cpu_cores": 2, "memory_mib": 4096},
    }
    (dest / "eval_public.json").write_text(json.dumps(public, indent=2) + "\n")
    # A synthetic baseline enables diff submission without any upstream history.
    git_env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_AUTHOR_DATE="2019-08-30T00:00:00+00:00", GIT_COMMITTER_DATE="2019-08-30T00:00:00+00:00")
    for args in [["init", "-q"], ["add", "."],
                 ["-c", "user.name=Eval Baseline", "-c", "user.email=eval@invalid",
                  "-c", "commit.gpgsign=false", "commit", "-qm", "Evaluation baseline"]]:
        subprocess.run(["git", "-c", "init.templateDir=", "-c", "core.hooksPath=" + os.devnull,
                        "-c", "core.autocrlf=false", "-C", str(dest)] + args, check=True, env=git_env)
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(export(args.repo.resolve(), args.destination.resolve()))
