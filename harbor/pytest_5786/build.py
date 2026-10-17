"""Translate the original locked Eval; no maintained copy or scoring rewrite."""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT.parent / "pytest_5786"
BASE = "955e54221008aba577ecbaefa15679f6777d3bf8"
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT.parent.parent/"pytest")
    parser.add_argument("--output", type=Path, default=ROOT/"generated/pytest_5786")
    args = parser.parse_args(); out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((EVAL/"task.yaml").read_text())
    assert manifest["repository"]["base_commit"] == BASE
    assert json.loads((EVAL/"environment.yaml").read_text())["python"] == "3.8.20"
    lock = json.loads((EVAL/"checksums.json").read_text())["files"]
    for name, expected in lock.items():
        assert hashlib.sha256((EVAL/name).read_bytes()).hexdigest() == expected, name
    spec = importlib.util.spec_from_file_location("original_prepare", EVAL/"prepare.py")
    prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
    (out/"environment").mkdir(); (out/"tests").mkdir()
    prepare.export(args.repo.resolve(), out/"environment/workspace")
    shutil.copy2(EVAL/"instruction.md", out/"instruction.md")
    shutil.copy2(ROOT/"pytest_5786/task.toml", out/"task.toml")
    (out/"environment/Dockerfile").write_text("FROM pytest5786-runtime:py3820\nCOPY workspace /work\nWORKDIR /work\nENV PATH=/opt/pytest-python/bin:$PATH PYTHONPATH=/work/src\n")
    # Only generated context copies required by the original integrity check.
    # Do not vendor/rewrite the complete package under tracked harbor source.
    for name in ["checksums.json", *lock]:
        dest=out/"tests/eval"/name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(EVAL/name, dest)
    shutil.copytree(out/"environment/workspace", out/"tests/baseline")
    repo=out/"tests/repo"
    git_env=dict(os.environ,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull)
    def git(*argv): subprocess.run(["git",*map(str,argv)],check=True,env=git_env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    git("init","--bare",repo)
    git("-C",repo,"fetch","--depth","1","--no-tags",args.repo.resolve(),BASE)
    git("-C",repo,"update-ref","refs/heads/base",BASE)
    shutil.copy2(ROOT/"pytest_5786/verify.py",out/"tests/verify.py")
    (out/"tests/test.sh").write_text("#!/bin/sh\nset -eu\n/opt/pytest-python/bin/python /tests/verify.py\n")
    (out/"tests/Dockerfile").write_text("FROM pytest5786-runtime:py3820\nCOPY . /tests\nCOPY baseline /work\nWORKDIR /work\nRUN chmod +x /tests/test.sh\n")
    (out/"provenance.json").write_text(json.dumps(dict(base_commit=BASE,eval_lock_sha256=hashlib.sha256((EVAL/"checksums.json").read_bytes()).hexdigest(),source_files=lock,python="3.8.20"),indent=2)+"\n")
    print(out)
if __name__=="__main__": main()
