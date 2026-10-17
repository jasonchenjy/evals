import hashlib, json, os, socket, subprocess, sys
from pathlib import Path
out = Path("/logs/verifier")
agent = Path("/logs/artifacts/agent-hostname").read_text().strip()
base = subprocess.check_output(["git", "-C", "/base", "rev-parse", "HEAD"], text=True).strip()
assert base == "c273d4511362006a30b36447448cb4137eae1361"
assert base == Path("/logs/artifacts/agent-base").read_text().strip()
assert agent != socket.gethostname()
assert Path("/logs/artifacts/hidden-tests").read_text().strip() == "absent"
assert Path("/base/src/divide.py").read_text() == "def divide(a, b):\n    return a // b\n"
source = Path("/work/src/divide.py")
assert not source.is_symlink() and source.is_file() and source.stat().st_size < 65536
assert sorted(x.name for x in source.parent.iterdir()) == ["divide.py"]
patch = subprocess.run(["git", "diff", "--no-index", "/base/src/divide.py", str(source)], capture_output=True, text=True)
(out / "final.patch").write_text(patch.stdout)
sys.path.insert(0, "/work/src")
from divide import divide
checks = {}
for a,b in [(5,2),(-5,2),(1,4),(7.5,2),(6,3)]:
    try: checks[repr((a,b))] = divide(a,b) == a/b
    except Exception: checks[repr((a,b))] = False
try:
    divide(1,0)
    checks["zero"] = False
except ZeroDivisionError:
    checks["zero"] = True
result = dict(agent_hostname=agent, verifier_hostname=socket.gethostname(), base_commit=base, clean_base=True, hidden_absent=True, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), checks=checks, overall=all(checks.values()), infrastructure_status="ok")
(out / "result.json").write_text(json.dumps(result, indent=2)+"\n")
(out / "reward.json").write_text(json.dumps({"reward":float(result["overall"])}))
