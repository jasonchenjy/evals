"""Extract verified Homebrew bottle locally; never run brew install."""
import hashlib, io, json, tarfile, urllib.request
from pathlib import Path
root = Path(__file__).resolve().parent
sha = "4accfcfd6ebc0f7ef47db24b93447bd5e1751cc74b2e1874e8f2e11b0e02d806"
cache = root / "tools/buildx-bottle.tar.gz"
if not cache.exists() or hashlib.sha256(cache.read_bytes()).hexdigest() != sha:
    token = json.load(urllib.request.urlopen("https://ghcr.io/token?service=ghcr.io&scope=repository:homebrew/core/docker-buildx:pull", timeout=30))["token"]
    req = urllib.request.Request("https://ghcr.io/v2/homebrew/core/docker-buildx/blobs/sha256:" + sha, headers={"Authorization":"Bearer " + token})
    with urllib.request.urlopen(req, timeout=60) as source, cache.open("wb") as target:
        while chunk := source.read(1024*1024):
            target.write(chunk)
assert hashlib.sha256(cache.read_bytes()).hexdigest() == sha
with tarfile.open(cache) as archive:
    items = [m for m in archive.getmembers() if m.isfile() and m.name.endswith("/bin/docker-buildx")]
    assert len(items) == 1
    data = archive.extractfile(items[0]).read()
p = root / "tools/docker/cli-plugins/docker-buildx"
p.write_bytes(data); p.chmod(0o755)
(root/"evidence/buildx.json").write_text(json.dumps({"version":"0.38.0", "source":"Homebrew official arm64 bottle", "bottle_sha256":sha, "binary_sha256":hashlib.sha256(data).hexdigest()},indent=2)+"\n")
print("Verified and installed task-local Buildx", len(data))
