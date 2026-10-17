# Supervised pytest_5786 pilot

This entry point is independent of the earlier trusted-control-only adapter.
All changes and outputs stay under `harbor/`. It uses installed Harbor **0.24.0**,
Codex **0.162.1**, the original Eval package and Python **3.8.20**.
No original grader, hidden test, Oracle, or H02 rule is changed.

## Execution boundary

The supported Harbor Environment adapter retains Docker/Compose lifecycle and
exec. It uses a fixed Docker `none` or `bridge` network, rejecting dynamic policy
changes and allowlists. Controls and all grading workers use `none`. The proposed
Codex container uses `bridge`: candidate commands have the same network access as
the model client. This is an explicit approval requirement, not endpoint isolation.

The Agent runs as UID 1000 with zero effective capabilities and no-new-privileges.
The root filesystem is read-only. Four bounded tmpfs mounts provide working space,
home, temporary files and logs (1984 MiB total plus 16 MiB shm). CPU=2,
memory=4 GiB without swap, PID limit=128, individual file limit=32 MiB, transport
output limit=16 MiB and wall budget=1800 seconds. There are no host mounts, ports,
host PID namespace, Docker socket or devices. Trusted PID 1 and controller exec
retain only CAP_KILL to terminate candidate descendants; candidate exec does not
receive that capability. Host control remains outside the container.

The `AGENT_END` hook stops and kills every process whose kernel-reported UIDs
include 1000. It checks `/proc/*/status`, not directory ownership (a nondumpable
process changes its /proc ownership). The root-owned immutable system interpreter
then checks source inode types, link counts and sizes. No candidate process remains
running while collecting. The archive transport is bounded and parsed without
`extractall`: links, devices, FIFOs, duplicate paths, traversal, non-UTF8 Python,
unexpected executable bits and size excess are rejected. Non-Python regular files
are excluded. Python files are limited to 2 MiB each / 16 MiB total, with at most
10,000 entries. Local fake/Git tests also exercise hostile candidate Git metadata.

The original `runtime/submission.py` reconstructs a trusted baseline and makes the
patch without invoking candidate Git. A thin normalization handles group-write
bits changed by Git/umask; executable changes remain rejected. The verifier applies
the patch to another fresh export and compares the **entire** allowed source tree,
not just the changed files, with the frozen source hashes.

Harbor creates a separate public-only verifier environment and calls our supported
`BaseVerifier` adapter. The original `grade()` stays on the host; `runtime/grading.py`
intercepts every candidate Python invocation and delegates to the existing
`ContainerSandbox`. These workers are nonroot, read-only, network-none, resource
bounded, mount-free containers, each discarded after its check. They receive only
the reconstructed candidate, original behavioral check files and dependencies.
Oracle patches, the Eval lock, credentials and trusted result files remain on the
controller. `trusted_local=True` only enters legacy orchestration; it is never the
execution boundary, and there is no unrestricted execution fallback.

This still does not prove resistance to a candidate manipulating the check
interpreter or forging semantically valid observations. Tests execute candidate
Python in the same worker process. The supported claim is host/result-file and
Oracle isolation for a supervised MVP, not production anti-cheating equivalence.
It also does not provide a host-crash watchdog or a new authentication service.

## Authentication decision

Installed Harbor's `Codex.run` uploads auth.json and runs candidate commands as the
same uid. API-key authentication writes its key to that same container as well;
it is not a credential-isolated alternative. No small supported out-of-container
credential/execution split was established in this installed adapter. We did not
build a gateway or weaken the container capabilities to make authentication work.

`PilotCodex` inherits the native run, prompt, fresh-session and trajectory handling.
Its root-exec adjustment permits only the native auth ownership command and the
exact config ownership + `chmod 600` command, executing both as UID 1000,
because our bounded upload already creates those files as that uid. Runtime package
installation as root is forbidden; the exact CLI is preprovisioned in the image.

The fake-auth preflight proves that candidate commands **can read the injected
credential**, and that arbitrary shell TCP egress works. Real authentication needs
explicit approval for one `openai/gpt-6.1-sol` trial with this exposure and public
network access. Existing synthetic-trial authorization does not count.
Mitigations: one fresh 30-minute container, no inherited config/conversation or host
mounts, only the selected Codex credential, ephemeral writable files, native auth
cleanup followed by container destruction, credential scanning before curating
traces, no retry. These reduce lifetime and scope; they do not prevent credential
theft or exfiltration during the trial. A dedicated revocable credential is safer
than the main account auth.json and may be supplied instead.

## Reproduction on this host

Use the existing Colima socket explicitly. `--image` is the immutable image ID;
the runner creates a uniquely named local tag only because BuildKit's FROM cannot
consume a bare image ID. Worker builds retain Docker's legacy immutable-ID mode.
Local Compose/Buildx are symlinks to the already-installed Docker CLI plugins;
no Docker Desktop policy, VM configuration or global Docker settings are changed.

```sh
harbor/.venv/bin/python -B harbor/pilot/build.py \
  --image sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12 \
  --output harbor/generated/new-controls
harbor/.venv/bin/python -B harbor/pilot/run.py \
  --task harbor/generated/new-controls --output harbor/raw/new-qualification \
  --image sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12
harbor/.venv/bin/python -B -m unittest discover -s harbor/tests -v
```

Run `probe.py`, `worker_checks.py` and `live_preflight.py` using their `--help`
interfaces for the agent/resource checks, original worker adversarial checks and
fake-auth-only live-image test. That preflight enters the native `Codex.run` path,
checks config permissions, the auth link, fresh-session state and native cleanup,
and intercepts the model command before execution. It makes no model call and
cannot validate backend login or model availability. All outputs must be new;
preserve prior attempts.
The live task builder needs `--live --codex <preprovisioned Linux binary>`.

Live execution requires `--live --model ... --auth-file ...`, passing paths for
`--qualification`, `--security`, `--worker-checks`, `--preflight`, plus both
`--approve-container-credentials` and `--approve-public-network`. The flags record
an **already obtained human approval**, never create authorization themselves.
The runner checks both qualifying and native-preflight adapter hashes before
invoking the model. The older setup-only preflight is no longer sufficient.
Use no `-O`; optimized Python is refused. Do not rerun a live attempt to improve
the coding score. Curate using `harbor/curate_pilot.py`; do not commit raw workspaces,
transport archives, auth files or generated images.

The Runtime helpers are read-only dependencies pinned by `runtime-lock.json`.
Concurrent changes fail closed. Review and requalify before updating that lock;
do not copy or rewrite the Runtime package. Harbor now owns trial orchestration,
while the existing security components remain necessary.

## Recorded live attempt

The one approved attempt `pilot-real-01` stopped before `codex exec`: the original
ownership allowlist rejected Harbor's combined config `chown`/`chmod` command.
The selected credential had already been injected; the container was removed.
Its empty recovery patch is not a model submission, and no grader scores exist.
The compatibility fix and expanded fake-auth preflight are verified separately.
There has been no second real attempt. See `../PILOT_REPORT.md` for evidence and
the remaining end-to-end limitation.
