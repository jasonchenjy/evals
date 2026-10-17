#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3.13 -m venv harbor/.venv
harbor/.venv/bin/pip install -r harbor/requirements-controller.lock
mkdir -p harbor/tools/docker/cli-plugins harbor/tools/home
curl -fLsS --connect-timeout 15 --retry 3 --max-time 600 https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-darwin-aarch64 -o harbor/tools/docker/cli-plugins/docker-compose
python3.13 -c 'from pathlib import Path; import hashlib; p=Path("harbor/tools/docker/cli-plugins/docker-compose"); assert hashlib.sha256(p.read_bytes()).hexdigest()=="bd714a42b46e51757fc1121085b3096b9064e3f80d3ca5a991e33f44df4f43c9"; p.chmod(0o755)'

python3.13 harbor/setup_buildx.py
