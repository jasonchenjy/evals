# pytest_5786 single-task runtime

**Status: PARTIALLY_READY.** The selected next-stage boundary is Colima VZ + Docker Engine on Linux arm64. Linux grading, finite resource limits and hostile file handoffs have been verified; the real Codex pilot is still NOT_EXECUTED. See [container pilot readiness](container_readiness_report.md) and [reproduction commands](container/README.md). No live gate was removed.

The sections below describe the retained native baseline. Exact exports, historical tests, source collection and the existing private grader run through native macOS workers. Real Codex participant execution is deliberately blocked until the effective tool inventory, dedicated authentication and adequate resource/descendant containment are verified. No real agent pilot has run. This is one Eval, one CLI harness and sequential execution, not a provider framework.

Use Python3.8+ for the controller, the existing CPython3.8.20 venv for workers, macOS with CommandLineTools Git, and the tested Codex CLI0.162.1. Pin the executable rather than implicitly using the newer desktop-bundled CLI. No packages are installed by the runtime.

From the `evals` checkout:

```sh
python3 -B runtime/run.py \
  --eval pytest_5786 --repo ../pytest \
  --python pytest_5786/.venv/bin/python \
  --codex /Users/junyuc/.codex/packages/standalone/releases/0.162.1-aarch64-apple-darwin/bin/codex \
  --model gpt-6.1-sol --preflight-only --output runs/my_preflight
```

`--output` must be new. Preflight invokes no model. It records independent agent/grading canaries, source/environment checks, bounded termination/output probes, actual fresh prompt input and supported login status. Exit2 means prerequisites remain blocked; inspect `result.json` and its `blockers` even when status is `not_executed`. Removing `--preflight-only` requests a real trial, but current code rejects it before any model call because the safety gates remain unsatisfied. There is no unsafe/bypass flag.

Run this trusted controller from outside a pre-existing nested Seatbelt sandbox. **Candidate commands still run in the strict inner sandbox.** A nested launch failure is infrastructure failure; the runtime never retries a candidate unrestricted. The investigated machine required an explicitly approved outer controller launch from Codex development tooling.

Deterministic validation:

```sh
python3 -B -m unittest discover -s runtime/tests -v
python3 -B runtime/probe.py --eval pytest_5786 --repo ../pytest \
  --python pytest_5786/.venv/bin/python --output runs/native_probe
python3 -B runtime/qualify.py --eval pytest_5786 --repo ../pytest \
  --python pytest_5786/.venv/bin/python --output runs/native_qualification
```

`qualify.py` runs the seven *existing trusted* control patches and original grader contract tests. It is not an agent trial and does not call a model. Oracle patches stay controller-side; workers receive freshly patched source and just the check files they require.

## Files and stage contracts

- `core.py`: verify locked Eval/source identities; call existing prepare.py; audit payload/Git baseline; bounded subprocess capture. Inputs are trusted Eval/source paths; outputs are provenance/export/logs. Missing commit, bad hash or export mismatch aborts.
- `sandbox.py`, `worker.py`, `canary.py`: generate the actual native permissions policy, clean environment, minimal runtime mappings, public environment checks and enforced canary checks. Startup failure/failed canary aborts. A tiny isolated Python bootstrap installs CPU-seconds/file-size limits before candidate Python can import its sitecustomize.
- `agent.py`: fresh CLI argv, configurable model, isolated controller home, public task prompt, disabled web/apps/plugins/browser/memory/skills, prompt audit, JSONL/final-response paths. A missing tool/context/auth/containment gate prevents invocation.
- `submission.py`: copy audited source into a pristine mirror, diff the controller's recorded baseline, invoke original validate_patch, and verify applied bytes. Never trust candidate HEAD/index/config/attributes/hooks. Empty diff is a valid no-op. Mode/symlink/path/encoding violations are invalid submissions.
- `grading.py`, `handoff.py`: keep controller artifacts outside worker scratch, safely capture/validate bounded observation files through pinned directory descriptors, then pass a controller-owned copy to the unchanged grader. Unsafe handoffs and worker startup failures are infrastructure errors. No Eval file or integrity lock is changed.
- `container_boundary.py`, `container_sandbox.py`, `container_worker.py`: the selected container candidate executor, effective-policy validation, immutable input-image mapping, byte-only transport, and full container lifecycle cleanup. This is a grading/probe adapter, not a verified live Codex harness.
- `run.py`: stage transitions and result/summary output. `probe.py` and `qualify.py` are deterministic acceptance commands.

The original grader requires `trusted_local=True` to enter trusted orchestration. The adapter supplies that argument **only while every Python execution call is intercepted by the mandatory sandbox launcher**. It does not invoke `--trusted-local` as isolation or execute candidate Python directly on the controller. Original `result.json` retains its legacy security-mode label; adjacent `runtime_execution.json` records the actual worker boundary, file hashes and limitations. This avoids changing grading semantics or historical evidence.

## Actual boundaries and remaining gates

The generated profile uses `:workspace`, denies root/shared tmp reads, permits `:minimal`, the exact venv/interpreter directories and the actual CLT Git binary read-only, and permits only its own scratch. Candidate commands have no network. `.git` writes are protected. Native environment uses GIT_CONFIG_NOSYSTEM=1 to prevent CLT Git from reading its global configuration. The controller records the full actual permissions string per execution; no global configuration is edited.

By default, agent controller HOME/CODEX_HOME is new, has no developer history, and is denied to candidate commands. Optional `--client-home /dedicated/runtime-client` allows a purpose-created controller home provisioned through supported Codex login to be reused for authentication across fresh ephemeral sessions; the developer HOME and any authentication home inside candidate-readable paths are rejected. Its rendered prompt must still pass the same audit. No auth files are copied. Supported `login status` confirms it is unauthenticated on this machine; use the supported login flow only after the remaining safety design is accepted. Do not put credentials into worker environment variables or source folders.

Native baseline: prompt introspection initially exposed four vendor system skills despite skip_host_skill_discovery. They are now disabled through exact **SKILL.md** paths; the fresh rendered prompt has no skill catalog or prior developer conversation. The inspected CLI debug surface returns prompt items, **not actual tool definitions**. The new rejecting local fixture captures actual request serialization, including `input[].additional_tools`: disabled-feature flags still leave collaboration and MCP resource entry points exposed. This is explicit failing readiness evidence, not approval to run a participant. Tool availability and file-tool enforcement therefore remain unverified. The live gate cannot be opened just by editing a JSON result.

Implemented/enforced: wall deadline,8MiB combined stdout/stderr cap, ordinary owned process-group kill/reap, per-process CPU seconds and32MiB maximum individual file size in workers. CPU seconds do not mean2 cores; a file cap is not a2GiB filesystem quota. Aggregate RAM/PID/disk limits and detached descendants are not contained by the demonstrated native mechanism. Native agent-generated commands also do not automatically inherit the worker wrapper's rlimits. This is an explicit reason not to claim safe untrusted trials yet.

Private grading inputs are only fresh patched source; staged check.py, behavior.py, existing_inventory.json and public requirements; exact dependencies; its scratch. Staged immutable inputs are read-only under Seatbelt. Oracle/research/full Eval/other trials/controller-home are denied. Candidate code still shares a Python interpreter with checks and can inspect/interfere with it; this is not an adversarial anti-cheating system.

## Results and evidence

Statuses: `resolved`, `unresolved`, `invalid_submission`, `agent_timeout`, `infrastructure_failure`, `not_executed`. A negative code score is separate from a launcher/environment failure. Overall is null when no grading ran. Every started controller attempt writes result.json even on failed prerequisites; an existing output directory is rejected without overwriting it.

Raw `runs/` remain local/ignored because they include repository exports, per-run scratch and dedicated client homes that may later hold authentication. Small reviewed results/logs are copied to `runtime/evidence/`. Runtime source hashes and Eval lock identity accompany the selected evidence. Do not publish an authenticated client home or feed private results back to the participant.

Read [implementation_report.md](implementation_report.md) for exact executed commands, final deterministic results, preserved failed attempts and next steps.


## Controller/worker file handoff

Worker scratch is separate from controller stdout/stderr, combined logs, execution records and the legacy grader observation path. The native policy denies controller capture directories explicitly; the launcher rejects writable-root overlap and unsafe directory ancestry. File transfer uses directory-relative no-follow opens, nonblocking regular-file checks, a 1 MiB observation limit and schema validation. Controller publication uses private temporary files and atomic replacement; no worker-controlled link is followed. Missing output retains the original execution-error/timeout behavior; present unsafe or malformed output aborts as infrastructure failure.

The [handoff security report](handoff_security_report.md) records the pre-fix regression, final 22 runtime tests, 7 original grader contracts, all seven unchanged qualification outcomes, and a real native hostile-handoff probe. Reproduce that fake-data-only probe from a trusted outer controller:

```sh
python3 -B runtime/probe_handoff.py --eval pytest_5786 --repo ../pytest \
  --python pytest_5786/.venv/bin/python --output runs/native_handoff_regression
```

This probe deliberately creates an unsafe observation. Success means the worker was actually isolated, the fake protected file remained unchanged, no fake content leaked, and grading rejected the handoff as an infrastructure error. It is separate from the seven normal qualification controls and consumes no model call.
