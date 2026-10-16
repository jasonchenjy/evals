# 2026-10-16 Colima/Linux experiments

These are deterministic runtime experiments and qualification controls, **not an
Agent Trial**. Readiness remains `PARTIALLY_READY`; real model calls are zero.
The requested pilot model is `gpt-6.1-sol`. No participant patch or ability score
exists. `tool_inventory.json` says PASSED for **request capture**, while its live
tool-enforcement and dynamic-inventory gates remain false.

## Included evidence

- `experiment_index.json`: run purposes, local raw directories, preserved failed
  loopback-bind attempt and links to the final published evidence.
- `runtime_tests.log`: 29 passing runtime tests; `grader_contract_tests.log`: 7
  passing original grader contract tests.
- `qualification_summary.json`, `qualification_comparison.json`: all seven
  controls and exact comparison of all 91 check statuses with the prior baseline.
- `controls/<name>/result.json` and `runtime_execution.json`: unchanged copies of
  each control's complete grader result and execution-boundary record. Original
  legacy security-mode labels are retained; the adjacent adapter record identifies
  the actual container boundary. These are curator-only records.
- `environment.json`, `public_{serial,xdist,sanity}.*`: actual interpreter,
  dependency versions, exported pytest location, public test output and commands.
  Serial/xdist reproducer exit 1 is the expected failing baseline behavior.
- `resource_results.json`, `resource_receipts.json`, `resource_runs/`: finite
  aggregate-memory/PID/storage/network probes, effective Docker policy, bounded
  timeout/output, detached-child cleanup, and fresh-container state reset.
- `filesystem_canaries.json`, `handoff_results.json`, `handoff_rejections/`:
  real container isolation and ten handoff cases, including eight expected unsafe
  handoff rejections. These are separate from normal qualification controls.
- `tool_inventory.json`, `wire_request_excerpt.json`, `inventory_fixture.*`,
  `request_identity.json`: actual serialized tool definitions and public prompt
  captured by a rejecting loopback fixture. The excerpt copies selected request
  fields unchanged. It excludes headers and bundled default instructions, and
  includes the SHA-256 of the complete local request. No inference or tool calls
  were returned by the fixture. Extra collaboration/MCP resource tools remain a
  blocker, not proof of enforced tool restrictions.
- `dedicated_auth_status.json`: supported CLI status command returned exit 1.
  No authentication file was opened or published.
- `engine.json`, `integrity.json`, `readiness.json`: environment identity,
  immutable Eval/source hashes and explicit remaining gates. The dedicated VM was
  stopped after validation, preserving disks/images while releasing RAM.

The original complete raw runs remain under ignored
`runs/pilot_readiness_20261016/`. Credentials/client homes, VM state, downloaded
binaries, dependency caches and generated source workspaces are deliberately not
published. Original absolute paths in evidence are provenance, not portable
filesystem dependencies. Files copied from earlier stages are not relabeled as
having run against later edits; their original execution/source hashes remain.

Reproduction: [commands](../../container/README.md). Interpretation and limits:
[Chinese report](../../container_readiness_report.md). Every file in this folder
is covered by [runtime/artifact_hashes.json](../../artifact_hashes.json).
