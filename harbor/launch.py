"""Task-local environment for Harbor, Docker and cache; no global config edits."""
import os, sys, subprocess
from pathlib import Path
root = Path(__file__).resolve().parent
os.environ.update(DOCKER_HOST="unix:///Users/junyu/.colima/default/docker.sock", DOCKER_CONFIG=str(root/"tools/docker"), HOME=str(root/"tools/home"), PYTHONDONTWRITEBYTECODE="1", PATH="/opt/homebrew/bin:"+os.environ["PATH"])
(root/"tools/home").mkdir(parents=True, exist_ok=True)
image = subprocess.check_output(["docker", "image", "inspect", "pytest5786-runtime:py3820", "--format", "{{.Id}}"], text=True).strip()
if image != "sha256:1734efd60ea49a9bef74be6943cf0845625048f2ba59b36461fdb78a3f8cc9a9":
    raise SystemExit("Base image changed; requalify before use: " + image)
os.execv(str(root/".venv/bin/python"), [str(root/".venv/bin/python"), str(root/"run.py"), *sys.argv[1:]])
