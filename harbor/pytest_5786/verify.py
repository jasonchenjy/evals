"""Restore only source changes, call the unchanged grader, translate results."""
import hashlib, importlib.util, json, os, socket, stat, subprocess, sys
from pathlib import Path
out=Path("/logs/verifier")
agent=Path("/logs/artifacts/agent-hostname").read_text().strip()
assert agent != socket.gethostname()
assert Path("/logs/artifacts/hidden-tests").read_text().strip()=="absent"
original=Path("/tests/baseline")
assert subprocess.check_output(["git","-C",str(original),"rev-parse","HEAD"],text=True).strip()==Path("/logs/artifacts/agent-base").read_text().strip()
expected=json.loads(Path("/tests/eval/base_files.json").read_text())
for name, digest in expected.items():
    assert hashlib.sha256((original/name).read_bytes()).hexdigest()==digest, name
src=Path("/work/src")
for p in src.rglob("*"):
    mode=p.lstat().st_mode
    assert not p.is_symlink(), str(p)
    if p.is_dir(): continue
    assert stat.S_ISREG(mode) and p.suffix==".py", str(p)
    base_file=original / p.relative_to(Path("/work"))
    expected_execute=(base_file.stat().st_mode & 0o111) if base_file.exists() else 0
    assert mode & 0o111 == expected_execute, str(p)
    assert p.stat().st_size<=1024*1024, str(p)
    p.read_text(encoding="utf-8")
version="src/_pytest/_version.py"
assert (Path("/work")/version).read_bytes()==(original/version).read_bytes()
env=dict(os.environ,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull)
subprocess.run(["git","-C","/work","add","-N","src"],check=True,env=env)
patch=out/"final.patch"
patch.write_bytes(subprocess.check_output(["git","-C","/work","diff","--no-ext-diff","--no-textconv","--","src"],env=env))
# Original grader validates allowed paths, creates a fresh original snapshot,
# checks exact Python/dependencies, applies the patch, and scores all dimensions.
command=["/opt/pytest-python/bin/python","/tests/eval/private/grader.py","--repo","/tests/repo","--python","/opt/pytest-python/bin/python","--patch",str(patch),"--output",str(out/"grader"),"--trusted-local"]
with (out/"grader-stdout.txt").open("w") as log:
    process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
result=json.loads((out/"grader/result.json").read_text())
identity=dict(agent_hostname=agent,verifier_hostname=socket.gethostname(),fresh_base_verified=True,base_commit=result["base_commit"],hidden_absent=True,grader_returncode=process.returncode,grader_unmodified=True,network_policy="no-network",scope="trusted deterministic controls; not hostile-submission qualification")
(out/"isolation.json").write_text(json.dumps(identity,indent=2)+"\n")
assert result["infrastructure_status"]=="ok", result.get("error")
assert result["submission_status"]=="accepted",result.get("error")
assert process.returncode==(0 if result["overall_resolved"] else 1)
for name,digest in result["applied_source_sha256"].items():
    candidate=Path("/work")/name
    assert (hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.exists() else None)==digest
reward={"reward":float(result["overall_resolved"])}
reward.update({k:float(v["satisfied"]) for k,v in result["dimensions"].items()})
(out/"reward.json").write_text(json.dumps(reward,indent=2)+"\n")
