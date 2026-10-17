# Stage 4.1 preflight

Status: **AUTHORIZATION_REQUIRED**. Offline packaging and qualification passed;
zero real B/C model calls and no real authentication used. Approval for the
historical A pilot does not authorize these experiments. Exactly one fresh B
and one fresh C Trial have been requested, with no automatic retries.

## Twelve gates

1. B is grounded in the original issue title/body. See `original_issue.json` and
   `source_reference.md` for the retained symptoms and editing decisions.
2. C states the observable chain-reporting defect without implementation hints.
3. Both generated instructions append the exact same operational appendix.
   `inputs.json` binds component hashes and complete combined instructions.
4. Both supply a reproducible discrepancy, expected preservation, editable source,
   public examples, working commands and a submission contract. They are
   sufficiently specified for an engineering investigation; hidden compatibility
   requirements remain ordinary existing-behavior constraints rather than clues.
5. Actual B/C filesystems were inspected before authentication. Each has 14,229
   file/link entries and 448 public files in each workspace copy. Only TASK.md
   differs among public files. `inventory-comparison.json` lists every full-system
   difference: instruction copies, derived Git metadata, Docker hosts/hostname.
6. No iteration/private directories, hidden tests, Oracle/control patches, prior
   submissions/trajectories, grader, analysis or experiment results were found.
   Each actual /work and /base Git store has one commit, no remotes/alternates,
   no unreachable objects and no historical Gold commit. Known private-material
   fingerprints were checked against all readable regular files. Full inventories
   are in `evidence/preflight-{B,C}/visible-inventory.json`.
7. All pinned upstream source files match the original package at base commit
   `955e54221008aba577ecbaefa15679f6777d3bf8`. A new synthetic Git commit records
   each instruction, without upstream history. Original trusted collection still
   uses the original synthetic source baseline; source bytes are unchanged.
8. Actual containers passed Python 3.8.20/default and non-login shell checks,
   pinned-dependency checks, and serial/xdist public reproductions. Their two
   expected failures expose the unfixed bug and are not preflight failures.
9. Codex 0.162.1 native read/search/edit/exec, apply_patch, PTY resume and nonzero
   exit handling passed through the existing local scripted Responses fixture.
   It made no real model calls. This checks tool plumbing, not model capability.
10. A harmless source-only edit passed collection and byte-exact transfer to a
    separate verifier in both preflights. Existing freeze/quiesce, worker, timeout
    and source restrictions remain active. No independent grader was replaced.
11. Eval v0.1.0 and its original 21-file lock are unchanged. The eight reused
    Runtime helpers and 14 shared Harbor adapter/control files match their
    qualified identities. Original mandatory checks remain A01/A02, B01–B03,
    C01–C03, D01–D03. H02 remains diagnostic-only; Stage 4 controls are not added.
12. Both configurations select openai/gpt-6.1-sol, Harbor 0.24.0, Codex 0.162.1,
    1800 seconds Agent and a separate 1800-second verifier budget, same pinned
    image/dependencies/resources/features, fresh sessions, no retry loop. Actual
    model identity remains unobserved until authorized execution.

## Packaging repair and provenance

Simply changing the top-level prompt would leave A's detailed instruction in
`environment/base/TASK.md`. Public `eval_public.json` also contained the capability
label. The experiment builder replaces both instruction copies, removes only that
label, and rebuilds the copied synthetic Git store so old instruction blobs cannot
be recovered. It does not modify the original Eval, template, verifier or history.

`experiment.py` is a small overlay on the existing Pilot, not a new runner. It
first validates the original qualified template with the original validator, then
requires the exact frozen variant task manifest, source inventory, bundle, Eval
identity and experiment code hashes. Only the public-container Git check uses the
new participant baseline. The trusted collector retains its original baseline.
The original qualification/security/worker/preflight gates still execute. The
actual filesystem gate also runs at each future live Agent start before credentials
are uploaded. Six focused provenance/authorization guard tests passed.

Reused evidence: `harbor/raw/pilot-readiness-qualification-final` (7 controls and
91 comparisons), `harbor/raw/pilot-security-final`, and
`harbor/raw/pilot-worker-handoff`. Existing environment evidence supplies the
qualified template identity. Only packaging-dependent offline checks were rerun;
no expensive full control qualification was repeated.

`inputs.json` SHA-256:
`225fe767d7c15be3f1f174c8fcc73cba6d7c200c8af6f3c3935c1bb6e51aceaf`.
Combined B instruction SHA-256:
`15d7e30ab6d1ff8d9da1d90972b6cb50d7908dea3fdfef9c0a30c59d765fae61`.
Combined C instruction SHA-256:
`2ff5cdc2a44941e190a9780a8286f1ae5dc9f82f65e36a768b525f5b69da08f7`.
Complete generated task manifest hashes and individual file hashes are in
`inputs.json`; actual inventory hashes are in `inventory-comparison.json`.

## Scope and remaining authorization

The inventory hashes every persistent regular file readable by candidate UID 1000,
records links and unreadable paths, and excludes virtual /proc, /sys and /dev.
The 16 unreadable system-path records are retained, not claimed to be inspected
contents. No extra readable non-system payload outside /work and /base was found.
This establishes local packaging isolation; it does not exclude training exposure
or obtaining public historical answers over the network.

Installed Harbor's native Codex adapter uploads the selected auth file to
`/tmp/codex-secrets/auth.json` and links `/home/agent/.codex/auth.json` to it.
The solving process and candidate shell commands run as UID 1000 and can read
this file. Public egress is available to both. Cleanup removes the temporary
credentials/container but cannot revoke a credential already copied out. Dedicated,
revocable credentials are preferred. Preflight verified these mechanics using
fake authentication, without reading or saving real authentication contents.

Fresh explicit approval must name the credential file and authorize exactly B/C,
one each, container credential exposure and public network access. Command-line
approval flags are enforcement inputs, not evidence of human authorization.
Until approval arrives, both live Trials remain NOT_RUN, not failed evaluations.
