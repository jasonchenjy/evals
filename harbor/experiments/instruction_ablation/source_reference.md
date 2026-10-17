# Original issue and instruction construction

Primary source: [pytest issue #5786](https://github.com/pytest-dev/pytest/issues/5786),
“exception serialization should include chained exceptions”. The complete title
and issue body are preserved in `original_issue.json`, from the repository's
research snapshot retrieved at 2026-10-16T18:26:49.513646+00:00. The snapshot's
title/body, rather than the later detailed Eval instruction, supplied B. No PR
patch, comments, Oracle or diagnostic findings supplied its behavioral content.
The issue body's SHA-256 and source path are in that JSON; the entire JSON is
bound by `inputs.json`.

B retains the original title, both reproduction functions, explicit cause and
implicit context symptoms, the local/distributed discrepancy, `-n auto`, and
historical reproduction versions. It summarizes the long terminal transcripts
without copying paths, timing or unrelated session output. It makes the expected
preservation of exception information/relationships explicit and asks for a
source fix. The historical versions are labelled as context, not instructions
to replace the pinned environment. No collection, report-consumer, legacy
representation or captured-output requirements were added from the Eval.

C uses only the observable local/distributed discrepancy and the three-value
explicit-cause example. It asks for a source fix without breaking existing pytest
behavior. It names no implementation classes, modules or strategies. The shared
public reproducer still contains both cause and context examples, so implicit
context is discoverable in C even though it is absent from C's prose example.

The original title explicitly mentions serialization. That legitimate source
signal may aid B's root-cause discovery; B is not simply A with fewer words. B
also provides implicit-context examples more prominently than C. These are
semantic/context changes to analyze, not a pure length treatment.

`operational_appendix.md` is concatenated byte-identically after B and C, with a
blank-line separator. It supplies only paths, environment, public test commands,
submission restrictions and budgets. It does not point to the relevant source
modules or selected neighboring regression modules. `variant_a.md` is the exact
historical instruction, which interleaves behavior, compatibility expectations
and selected regression commands. A also exposed a capability label in public
metadata; B/C remove that label together. Thus A/B/C are not a perfectly
controlled single-variable experiment. B/C use otherwise identical packaging.

Instructions and package hashes were frozen before any B/C model call. Do not
revise them after seeing an outcome and count a rerun as an unbiased comparison.
