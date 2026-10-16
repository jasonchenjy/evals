# Colima worker reproduction

This is the single selected next-stage execution boundary. It currently supports
real resource/handoff probes and independent qualification grading. `run.py` still
fails closed before a live model turn. Do not use the following qualification
successes as a replacement for Codex tool-route/authentication gates.

Host prerequisites installed with user approval: Colima 0.9.1, Lima 1.2.1,
Apple VZ, Docker CLI 28.3.3. No Docker Desktop login or policy edit is required.
The dedicated VM uses 2 vCPUs, 6 GiB RAM, 8 GiB root disk and 12 GiB data disk
(sparse allocation). No HOME mount, SSH agent forwarding, global context change,
Kubernetes or Rosetta. The only host share is an empty read-only directory.

Commands below were executed for VM creation/build/qualification/probes, with
new output names as recorded in the report. The source-controlled Dockerfile
now pins the exact digest resolved by the original build. Apt packages are not
fully pinned: future rebuilds require a new image ID and requalification.

```sh
# One-time installation needs the user's host permission approval.
env HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew install colima
mkdir -p /private/tmp/pytest5786-colima-share runs/pilot-docker-client
# All Colima state is dedicated; no Desktop registry.json edits.
env COLIMA_HOME=/private/tmp/pytest5786-colima \
  DOCKER_CONFIG="$PWD/runs/pilot-docker-client" \
  colima start --runtime docker --vm-type vz --arch aarch64 \
  --cpus 2 --memory 6 --root-disk 8 --disk 12 \
  --activate=false --ssh-config=false --ssh-agent=false \
  --mount /private/tmp/pytest5786-colima-share \
  --vz-rosetta=false --kubernetes=false

# Trusted public dependency setup only; candidate containers have network=none.
/usr/local/bin/docker --host unix:///private/tmp/pytest5786-colima/default/docker.sock \
  --config "$PWD/runs/pilot-docker-client" build \
  --tag pytest5786-runtime:py3820 runtime/container
/usr/local/bin/docker --host unix:///private/tmp/pytest5786-colima/default/docker.sock \
  --config "$PWD/runs/pilot-docker-client" image inspect \
  pytest5786-runtime:py3820 --format '{{.Id}}'
```

The image actually used on 2026-10-16 was
`sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12`.
Use an immutable ID, never a tag, in worker invocations. Run these sequentially
from the `evals` checkout. Each output directory must be new:

```sh
python3 -B -m unittest discover -s runtime/tests -v
python3 -B runtime/probe_container.py \
  --endpoint unix:///private/tmp/pytest5786-colima/default/docker.sock \
  --client-config runs/pilot-docker-client \
  --image sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12 \
  --output runs/new_resource_probe
python3 -B runtime/probe_container_handoff.py --eval pytest_5786 --repo ../pytest \
  --endpoint unix:///private/tmp/pytest5786-colima/default/docker.sock \
  --client-config runs/pilot-docker-client \
  --image sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12 \
  --output runs/new_handoff_probe
python3 -B runtime/qualify.py --eval pytest_5786 --repo ../pytest \
  --docker-endpoint unix:///private/tmp/pytest5786-colima/default/docker.sock \
  --docker-client-config runs/pilot-docker-client \
  --container-image sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12 \
  --output runs/new_linux_qualification
python3 -B runtime/probe_cli_inventory.py --eval pytest_5786 --repo ../pytest \
  --codex /Users/junyuc/.codex/packages/standalone/releases/0.162.1-aarch64-apple-darwin/bin/codex \
  --output runs/new_rejecting_fixture
```

The fixture binds only loopback, records bodies (never headers), always rejects,
never forwards requests, returns no tool calls and performs zero inference.
It is not a pilot. Its local-provider configuration is not proof of identical
live-provider behavior. It detected unwanted tools in the actual serialized
request despite disable flags. The complete dynamically available tool set and
container routing remain unverified.

Dedicated authentication was requested from the user, not executed by the agent:

```sh
env HOME="$PWD/runs/pilot-client/home" \
  CODEX_HOME="$PWD/runs/pilot-client/home/.codex" \
  /Users/junyuc/.codex/packages/standalone/releases/0.162.1-aarch64-apple-darwin/bin/codex \
  -c 'cli_auth_credentials_store="file"' login --device-auth
```

Use `login status` to check completion. Never copy developer authentication,
include the client home in an image, or send a token/device code in chat.
The selected model is `gpt-6.1-sol`; it has not been invoked.

The candidate policy is checked against Docker inspect BEFORE start: nonroot,
no capabilities, no-new-privileges, read-only root, no mounts/ports/socket,
network none, 2 CPU quota, 4 GiB aggregate memory with no swap, 128 PIDs,
2047 MiB `/trial` tmpfs plus 1 MiB `/dev/shm`. All writable state is ephemeral.
The controller caps transport, then kills/removes the full owned container PID
namespace on normal completion, deadline and output overflow. Cleanup failure
is infrastructure failure; do not start another trial after such a failure.
A daemon outage/controller crash still needs an operator to stop the dedicated
VM; no crash-recovery watchdog has been claimed.

Private grader inputs are baked into a separate immutable image after host-side
patch validation/application. Builds execute only fixed COPY/chmod steps, never
candidate Python. Worker rootfs is immutable; workspace/scratch are fresh copies.
No Oracle patch, curator log, host credentials or controller directory is mounted.
The image bootstrap sends bounded byte envelopes after no-follow file capture;
the controller accepts them only after full-container termination and validates
observation again. Host paths are never taken from a worker envelope.
Candidate/check interpreter tampering remains outside this scoped security claim.

VM state is under `/private/tmp`, so an OS cleanup/reboot may remove it. Recreate
and requalify as needed; do not regard the running VM as a permanent deployment.
To stop only this dedicated VM and release its RAM:

```sh
env COLIMA_HOME=/private/tmp/pytest5786-colima \
  DOCKER_CONFIG="$PWD/runs/pilot-docker-client" colima stop
```
