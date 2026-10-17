# Coding workflow readiness preflight

This is an easy multi-file Python task used only to qualify Harbor's coding
workflow. It is not a new scored benchmark and does not ask the model to solve
pytest #5786. It uses Python's standard-library unittest runner.

The fixed public Git base is `adb1b8fe6fd81e25b880f3bdee2adb74e1ca306d`.
`sample_repo/src/` contains parser, validator and service modules. The service
loses the quantity field. The instruction asks for a normalization helper in a
new source file and a source fix. Public tests expose the bug. `private/` contains
independent hidden tests and correct/incomplete implementations for deterministic
controls. No private file enters the Agent image. The incomplete control passes
the public example but fails hidden checks on other inputs.

The runner uses actual Harbor 0.24.0 `Trial`, native `PilotCodex(Codex)` for the
real run, the existing Docker environment adapter, and `environment_mode=separate`.
The fixed-response tool fixture is a separate offline diagnostic; it is never
substituted for the genuine model trial. Controls use a clearly labeled scripted
agent. The complete control independently tests wrong edit → failing test →
correction → passing test, without forcing a genuine Agent to make a wrong edit.

Source collection reuses the pilot's stop/freeze/bounded archive handling. Patch
construction uses only the trusted fixed base, never candidate Git metadata.
The separate verifier starts clean, applies the patch, compares the entire
source inventory, receives only the hidden tests (not the known solution), and
runs them. Credentials, Agent home and non-source debugging files do not cross.
This supervised synthetic verifier is not a production anti-cheating boundary.

## Commands

From the evals checkout, first build the common runtime context and run its
fake-auth, zero-inference environment/tool preflight:

```sh
harbor/.venv/bin/python -B harbor/pilot/build.py \
  --image sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12 \
  --output harbor/generated/new-runtime --live \
  --codex runs/agent_colima_20261016/build/codex/bin/codex
harbor/.venv/bin/python -B harbor/pilot/live_preflight.py \
  --task harbor/generated/new-runtime --output harbor/raw/new-environment-check
harbor/.venv/bin/python -B harbor/preflight/build.py \
  --runtime-task harbor/generated/new-runtime --output harbor/generated/new-coding-controls
harbor/.venv/bin/python -B harbor/preflight/run.py \
  --task harbor/generated/new-coding-controls --output harbor/raw/new-coding-controls
```

Controls are sequential: No-op must fail, Complete must pass, Incomplete must
fail. Infrastructure errors are never accepted as expected failures. The complete
control includes only two harmless bounded processes for timeout/descendant
cleanup; no resource-exhaustion experiment is used.

Build the genuine task with the same builder plus `--live`. It differs only in
Agent network policy. It requires fresh explicit approval before supplying
`--live --auth-file <selected-file> --approve-container-credentials
--approve-public-network`, and requires passing `--qualification <controls-output>`
and `--pytest-preflight <environment-check-output>` paths. The default model is
`openai/gpt-6.1-sol`; the Agent and verifier each have a 300-second phase budget.
There is no automatic Trial retry. Use a new output directory for every invocation.

These flags record prior human authorization; they do not grant it. Native
Harbor copies the selected auth file into the temporary Agent container; candidate
commands run as the same UID and can read/exfiltrate it over public network.
Only the selected file is uploaded, not the host config or conversation. Native
cleanup and container destruction bound its lifetime. No real pytest Agent trial
is authorized or run by these commands.

`harbor/agent_readiness_report.md` distinguishes observed genuine Agent behavior,
scripted diagnostics and features still NOT_VERIFIED. Curated evidence uses
`harbor/curate_pilot.py`; raw workspaces, fake/real auth files and generated
contexts remain ignored. No push is part of this workflow.
