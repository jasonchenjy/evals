"""Build-context preparation only. Never copies authentication files."""
import argparse, hashlib, json, shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument("--vendor", type=Path, default=root.parent/"runs/executor-linux-verified/package/vendor/aarch64-unknown-linux-musl")
parser.add_argument("--output", type=Path, default=root/"generated/codex-spike")
args=parser.parse_args()
assert (args.vendor/"bin/codex").is_file()
assert not any(p.name in {"auth.json", "credentials.json"} for p in args.vendor.rglob("*"))
shutil.copytree(root/"spike",args.output)
shutil.copytree(args.vendor,args.output/"environment/codex")
p=args.output/"task.toml"
p.write_text(p.read_text().replace("[agent]\n", '[agent]\nnetwork_mode = "public"\n'))
p=args.output/"environment/Dockerfile"
p.write_text(p.read_text()+"\nCOPY codex /opt/codex\nRUN ln -s /opt/codex/bin/codex /usr/local/bin/codex\n")
(args.output/"codex-provenance.json").write_text(json.dumps({"version":"0.162.1", "binary_sha256":hashlib.sha256((args.vendor/"bin/codex").read_bytes()).hexdigest()},indent=2)+"\n")
