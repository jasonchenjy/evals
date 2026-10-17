# Frozen instruction ablation for pytest #5786

> Execution update: **BLOCKED**. The user authorized the two-Trial scope, but
> automatic approval review rejected main-account credential injection before
> process creation. No real Trial or model call occurred. The user selected a
> dedicated-credential alternative; its path and scope are still pending. See
> `execution_block.json`. The AUTHORIZATION_REQUIRED text below records the
> earlier offline checkpoint, not the current authorization state.


Current status: **AUTHORIZATION_REQUIRED**. B/C offline preflights passed. No real
B/C model Trial has run and prior approvals do not apply. No push is authorized.

Start with `source_reference.md`, `preflight_report.md` and `comparison_report.md`.
`baseline_a.json` indexes the historical A artifacts without altering them.
`inputs.json` contains complete qualified-template and variant task hashes;
`inventory-comparison.json` binds both actual container inventories and preflights.
`evidence/preflight-B` and `evidence/preflight-C` preserve curated receipts and
full accessible-filesystem inventories. Per-directory manifests hash each file.
The fake fixture's submissions and trajectory are offline qualification artifacts,
not B/C solving attempts. Raw outputs/generated trees are local and gitignored.

All commands below run from the evals repository root. Existing Colima endpoint,
Harbor environment, qualified template and native Codex bundle must be present.
The overlay configures the existing Docker environment; it creates no new Runtime.

```sh
harbor/.venv/bin/python -B -m unittest discover -s harbor/experiments/instruction_ablation/tests -v
```

Packaging was created once with `build_inputs.py`; the two preflights were run
with the existing Pilot via these commands, then compared:

```sh
harbor/.venv/bin/python -B harbor/experiments/instruction_ablation/experiment.py preflight --variant B --output harbor/experiments/instruction_ablation/raw/preflight-B
harbor/.venv/bin/python -B harbor/experiments/instruction_ablation/experiment.py preflight --variant C --output harbor/experiments/instruction_ablation/raw/preflight-C
harbor/.venv/bin/python -B harbor/experiments/instruction_ablation/compare_inventories.py
```

Existing output directories are immutable attempt records. Do not overwrite them
or rerun live attempts automatically. Rebuilding inputs requires fresh packaging
qualification; changing experiment execution code invalidates its frozen hash.

Only after fresh explicit approval for two Trials and a selected credential path:

```sh
harbor/.venv/bin/python -B harbor/experiments/instruction_ablation/experiment.py live --variant B --output harbor/experiments/instruction_ablation/raw/live-B-01 --auth-file APPROVED_LOCAL_AUTH_PATH --approve-container-credentials --approve-public-network
harbor/.venv/bin/python -B harbor/experiments/instruction_ablation/experiment.py live --variant C --output harbor/experiments/instruction_ablation/raw/live-C-01 --auth-file APPROVED_LOCAL_AUTH_PATH --approve-container-credentials --approve-public-network
```

The flags do not grant human authorization. Use only the approved file; never
print its contents. Each condition gets a fresh environment/session, 1800 seconds
Agent and separate 1800 seconds verification, the original grader, and no retry.
Classify any infrastructure failure separately. Do not edit prompts after results
or transfer one participant's trajectory/patch to another. Curate outcomes and
update the comparison after execution, preserving all earlier evidence. Commit
only verified experiment files, and do not push without explicit authorization.
