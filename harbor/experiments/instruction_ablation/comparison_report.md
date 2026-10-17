# A/B/C instruction ablation — offline report

> Execution update: **BLOCKED**. The user authorized the two-Trial scope, but
> automatic approval review rejected main-account credential injection before
> process creation. No real Trial or model call occurred. The user selected a
> dedicated-credential alternative; its path and scope are still pending. See
> `execution_block.json`. The AUTHORIZATION_REQUIRED text below records the
> earlier offline checkpoint, not the current authorization state.


Status: **AUTHORIZATION_REQUIRED**. This report records the historical A outcome
and the frozen B/C design. No B/C solving Agent has run; no B/C grades, timings,
patches or behavioral differences are available. Offline fixture actions must not
be interpreted as participant actions or capability scores.

## Conditions and fairness

A gives the chain defect plus explicit cause/context, collection failures,
captured output/sections, consumers, legacy representations and selected public
regression commands. Its exact text is `variant_a.md`; actual configuration,
instruction hash, trajectory/result/patch hashes and grading are indexed in
`baseline_a.json` and the unchanged historical evidence directory.

B preserves the original issue's serialization title and both cause/context
reproductions, observed local/xdist discrepancy and historical environment. It
omits later engineering requirements. C provides only the symptom and explicit
three-exception example, plus the general requirement to preserve pytest behavior.
B/C share identical operational instructions and public reproduction files.

Both appear fair and solvable: they identify a concrete observable mismatch,
provide a working environment, allow source investigation and supply public
reproductions. C's implicit-context case remains discoverable in the public file.
Broader compatibility obligations are less explicit than A's; a future failure
must be assessed against ordinary existing behavior and the wording, rather than
automatically classified as absence of cross-component reasoning.

B/C isolate behavioral instruction content after normalizing operational setup.
Across A/B/C, operations, highlighted test locations and capability metadata also
change. B's title provides a serialization clue, historical versions add context,
and examples differ in prominence. These are not merely length differences.

## Execution and grades

A used openai/gpt-6.1-sol, Codex 0.162.1 and Harbor 0.24.0. Agent duration was
52.897359 s, independent verifier 30.490934 s, whole Trial 91.387331 s. Recorded
trajectory: 14 steps, eight native exec calls containing 11 shell commands and
nine observed LLM calls. It inspected reports.py and _code/code.py, read public
report tests/reproductions, and changed only src/_pytest/reports.py. The source
patch was 6,986 bytes, 80 insertions and 41 deletions. Submission was accepted;
infrastructure status was OK.

A: Overall Resolved PASS; Original Bug Resolution PASS; Cross-Component
Consistency PASS; Edge-case Robustness PASS; Non-Regression PASS. Every mandatory
check passed: A01, A02, B01, B02, B03, C01, C02, C03, D01, D02, D03. H01 and H02
also passed and remain diagnostic. See `baseline_a.json` for individual outcomes.

B and C: NOT_RUN. Requested model/harness/budgets match A; actual duration, calls,
inspected/modified files, tests, patch size, submission and infrastructure outcome
are not available. Overall and all four dimensions are unmeasured; all 11
mandatory outcomes are NOT_RUN. This is an authorization wait, not a model or
infrastructure failure.

## Observable behavior

A searched the reporting and exception-representation modules, inspected both
sides of conversion, and changed serialization/deserialization together. Its
patch retained compatibility fields and supported legacy representations. These
are observable code/actions; they do not prove a particular internal reasoning
process or independent discovery rather than historical familiarity.

A ran distributed reproduction before and after editing, serial reproduction,
125 neighboring public tests, a temporary collection-failure example and a custom
120-case report round-trip diagnostic covering styles, report types, chains and
legacy forms. It corrected a tuple/list equality assertion in that temporary
diagnostic after JSON conversion and reran it successfully. That correction did
not require another source-patch change. Expected failing test cases still exit
nonzero when report rendering is correct. A's trajectory shows compatibility and
edge-case validation, but not inspection of every possible report consumer.

There is no B/C behavioral evidence yet, so no observed differences in root-cause
discovery, cross-component awareness, completeness, regression risk, testing,
time or tool usage can be attributed to instruction changes.

## Interpretation and next experiment

No current evidence establishes that detailed instructions caused A's success,
that minimal instructions reduce performance, or that this Eval is too easy.
The experiment did reveal a packaging confound: a prompt-only swap would expose
A through TASK.md/Git. Both copies and copied Git were repaired before execution;
the capability label was removed equally for B/C. The original Eval stays intact.

If all three pass, independent constraint discovery and model-task ease are
plausible explanations; neither instruction invariance nor training independence
is established by one run per condition. If only A passes, inspect which explicit
behavioral cues are absent and whether the omitted expectations remain fair. If
B passes and C fails, examine serialization-title and implicit-context examples.
Infrastructure failures are separate from valid coding failures. Timing/tool-use
differences alone have no demonstrated statistical significance at this sample size.

Public issue history, public network access and possible training exposure remain
uncertainties. Local Git sanitization does not eliminate them. Review future
trajectories for observed external retrieval, without treating its absence as
proof of no historical familiarity.

Next: obtain approval and execute the two frozen conditions once each. Then,
subject to separate authorization, preregister several independent runs with an
identical operational appendix and randomized condition order. Separate the
serialization-title cue from example coverage and explicit compatibility guidance
as distinct factors. For future Eval instructions, keep actionable symptoms,
expected user-visible behavior and neutral operations; avoid naming hidden checks
or internal implementation paths. Validate this design across additional bugs,
including less historically exposed tasks, before generalizing capability claims.
