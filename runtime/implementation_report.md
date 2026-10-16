# Stage 2 implementation report

**Final status: PARTIALLY_READY. Real Agent Trials: 0. Model calls: 0.**

Implemented a single-task native macOS controller in `runtime/`. It restores the fixed source, runs historical preflight and canaries under actual Seatbelt, builds fresh Codex CLI commands, collects source through a pristine mirror, and adapts the existing private grader's execution boundary. The deterministic pipeline works. The real participant path remains deliberately closed because tool enforcement, authentication and adequate aggregate resource/descendant containment are not all established.

## Preserved identities and Eval semantics

Eval commit: `02427af2b7e30e2c45332606070a9d09b86eb9e1`.
Core lock SHA256: `067f222eccfbf8d40fe520a7f4196426e82a4e5d4861e506cb96e60d11732e03` — see the exact canonical value in [integrity.json](evidence/stage2/integrity.json).
Source base: `955e54221008aba577ecbaefa15679f6777d3bf8`.
Synthetic baseline: `41ffd0de9c7ece927733fadc2201491c5ae51be2`.

All21 locked files still match. Neither the Eval package nor the trusted pytest checkout has a tracked change. No Oracle, mandatory check, threshold, dimension, H02 decision or historical qualification evidence was revised. Runtime files are new; `.gitignore` excludes raw runs and potentially authenticated controller homes. Curated evidence is retained beside the code.

Reused existing prepare.py, base_files.json, requirements, grader.validate_patch/git_apply/grade/summarize, check.py, behavior.py, existing_inventory.json and the original catalog. A small runtime adapter replaces `grader.run()` during one sequential grading call and restores it afterward. Trusted orchestration reads/checks Oracle materials; candidate execution cannot read them. No second scorer was implemented. The original grader's legacy security label is preserved with a separate actual boundary record.

## What was actually verified

- **A — restoration:** all443 base hashes, declared public payload only, clean single synthetic commit, no remotes/alternates/upstream commit object. No trusted checkout reset/clean.
- **B — environment:** CPython3.8.20 and all22 pins inside the strict native worker. pytest imports the export; serial contains all six exception messages; xdist starts gw0 and shows the expected baseline loss; public sanity passes. Intentional reproducer rc1 is accepted as expected behavior.
- **C — patch lifecycle:** existing-file edit, new Python file, deletion, no-op, debug/existing-test exclusions, actual byte equality after independent application, and clean re-export. Poisoned candidate HEAD/config/attributes are ignored. Symlinks/FIFO/mode changes and modified generated shim are rejected. Existing executable source modes are preserved instead of incorrectly rejecting the historical src/pytest.py.
- **D — isolation:** independent launch outside the development sandbox succeeded. Workspace source read/edit and Git read operations work; fake private/relative/cross-trial/shared-temp/credential reads and outside writes return EPERM. TCP connection is denied by policy, not inferred from DNS failure. Local IPC works. Private worker test inputs are readable but not writable. `.git` metadata writes are denied.
- **E — grading:** seven trusted controls reproduced the established boundaries through isolated workers. All infrastructure statuses are ok. No-op4/11,false; Historical9/11,false with C03/D03 errors; Complete11/11,true; Alternative11/11,true with H02 diagnostic failure; Last-only4/11,false; TestReport-only7/11,false; Text-only7/11,false. Original7 grader contract tests also pass.
- **F — invocation contract:** fresh exec argv includes configurable model, explicit workspace, no-daemon/ephemeral/ignore-config/rules, JSONL and final output; public prompt equality is checked. A clearly labeled fake CLI fixture verifies stdin/events/final-file plumbing without a model. Actual Codex debug prompt input was rendered and inspected in a separate controller home. Four initially injected system skills were disabled using exact SKILL.md paths; no skill catalog or developer conversation remains in the inspected prompt. This debug output does not enumerate actual tools, so tool enforcement is still NOT_VERIFIED.

**10 runtime tests passed;7 original grader contract tests passed;7/7 qualification controls matched expectations.** See [controller test log](evidence/stage2/controller_tests.log), [grader tests](evidence/stage2/grader_contract_tests.log), [qualification summary](evidence/stage2/qualification_summary.json), [complete control result](evidence/stage2/complete_control_result.json), [actual worker boundary](evidence/stage2/complete_execution_boundary.json), [agent canaries](evidence/stage2/agent_isolation.json) and [grading canaries](evidence/stage2/grading_isolation.json).

The native controller also demonstrated ordinary parent/child process-group termination after0.5s and a4096-byte output-cap probe. Production worker capture defaults to8MiB; the wrapper installs per-process CPU seconds and32MiB per-file size before candidate imports. These are real but limited controls, not aggregate RAM/PID/disk quotas or proof against detached descendants. [Resource evidence](evidence/stage2/native_resources.json).

## Commands executed

From this machine's SWE-bench workspace, with a separately approved outer controller for native integration:

```sh
python3 -B -m unittest discover -s evals/runtime/tests -v
python3 -B evals/runtime/probe.py --eval evals/pytest_5786 --repo pytest \
  --python evals/pytest_5786/.venv/bin/python --output evals/runs/stage2_native_04
python3 -B evals/runtime/qualify.py --eval evals/pytest_5786 --repo pytest \
  --python evals/pytest_5786/.venv/bin/python --output evals/runs/stage2_qualification_verified
python3 -B evals/runtime/run.py --eval evals/pytest_5786 --repo pytest \
  --python evals/pytest_5786/.venv/bin/python --model not-executed-contract-check \
  --preflight-only --output evals/runs/stage2_cli_preflight_final
python3 -B evals/runtime/run.py --eval evals/pytest_5786 --repo pytest \
  --python evals/pytest_5786/.venv/bin/python --model not-executed-contract-check \
  --output evals/runs/stage2_blocked_trial
```

The last command actually stopped at the agent gate, rc2, `infrastructure_failure`, grading not executed and overall=null. **It did not invoke a model.** The model string is a contract-test placeholder, not a claimed available model. Its [actual result JSON](evidence/stage2/example_result.json) demonstrates a preserved failed prerequisite rather than a fabricated successful trial.

Raw per-command argv, policy, durations, return codes, stdout/stderr, fixture details and snapshots remain in `evals/runs/`. Selected evidence totals roughly150KiB. Runtime source hashes are in integrity.json. Minor provenance/CLI-auth-home additions after the successful seven-control replay do not change worker or grader behavior; the blocked normal CLI validates the added provenance capture.

## Fixed implementation issues and retained failed attempts

Initial independent Git calls through `/usr/bin/git` attempted Xcode tool discovery. Using the installed CLT binary directly plus GIT_CONFIG_NOSYSTEM=1 fixed usability without opening extra host folders. Initial unit failures exposed executable baseline modes and incomplete recording of changed out-of-scope base files; both were corrected. No-op application now bypasses git apply's empty-input rejection as the existing grader does.

One replay (`stage2_qualification_final`) encountered a controller EOF/exit race: a check had passed, but post-output group cleanup briefly returned EPERM before waitpid observed exit. It is retained as invalid infrastructure evidence, not an Oracle failure. The runner now waits for actual process completion even after output pipes close. A focused closed-pipes regression passes; the subsequent full `stage2_qualification_verified` replay passes all controls. Earlier unit/native/qualification directories and logs remain intact.

## Remaining blockers and next step

1. **Effective tools:** rendered prompt items do not provide the actual Codex tool definitions or prove that native file tools and all execution surfaces honor the worker boundary. Configuration names and disabled feature flags are insufficient. The agent gate remains closed in code.
2. **Authentication:** supported login status in the dedicated controller home returns unauthenticated. No real credentials were read/copied/exposed. `--client-home` supports a purpose-provisioned reusable controller home for a later supported login; every participant would still use a fresh ephemeral session and workspace.
3. **Containment:** ordinary process groups cannot guarantee cleanup of detached children. Aggregate RAM/process/disk controls are not implemented; agent-generated commands do not automatically acquire worker-bootstrap rlimits. Native filesystem/network enforcement alone does not establish adequate containment for an untrusted participant. No unsafe override exists.

Next, resolve the actual Codex tool allowlist/enforcement path and complete the containment decision for the one-agent harness; use an existing additional execution boundary if native execution cannot meet it. Then provision dedicated authentication, select a model and run exactly one bounded pilot. No alternative virtualization platform was installed, no model was substituted, and no Eval was tuned to force a score.

This implementation supports deterministic runtime/Eval development now. It is **not yet ready to collect real model behavior for benchmark iteration**. Linux/other-platform qualification and adversarial resistance are not claimed; candidate code still shares an interpreter with the private assertions.
