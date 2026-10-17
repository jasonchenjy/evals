"""Copy bounded, reviewed evidence; never copy workspaces or credentials."""
import argparse, hashlib, json, re, shutil
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument("raw",type=Path);parser.add_argument("--name",required=True)
args=parser.parse_args();dest=root/"evidence"/args.name
dest.mkdir(parents=True,exist_ok=False)
selected=[]
for p in args.raw.rglob("*"):
    if not p.is_file() or p.is_symlink(): continue
    rel=p.relative_to(args.raw)
    if "workspace" in rel.parts or "artifacts" in rel.parts or "setup" in rel.parts: continue
    allowed=p.name in {"summary.json","config.json","lock.json","result.json","trial.log","exception.txt","reward.json","isolation.json","final.patch","initial-environment.txt","public-preflight.txt","control.txt","trajectory.json","codex.txt","test-stdout.txt","preflight.log","grader-stdout.txt","worker.log","observation.json"} or ("sessions" in rel.parts and p.suffix==".jsonl")
    if not allowed: continue
    assert p.stat().st_size < 8*1024*1024, p
    data=p.read_bytes(); text=data.decode("utf-8")
    for pattern in [r'"(?:access_token|refresh_token|id_token)"\s*:\s*"[^" ]{10,}"',r'\bsk-[A-Za-z0-9_-]{20,}']:
        assert not re.search(pattern,text), "Potential credential in " + str(p)
    target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    selected.append(dict(path=str(rel),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
(dest/"evidence-manifest.json").write_text(json.dumps(selected,indent=2)+"\n")
print(dest, len(selected), "files; credential-pattern scan passed")
