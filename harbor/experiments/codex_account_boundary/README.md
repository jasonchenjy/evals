# Codex account credential boundary

Latest result: **LIVE_ACCOUNT_BOUNDARY_PASS** — real Codex account, native CLI
0.162.1, `gpt-6.1-sol`, synthetic source edit and tests passed in 14.353 seconds.
Real credentials stayed outside the candidate. No API Key, B/C run or push.
See [live validation and limitations](LIVE_VALIDATION.md) and
[evidence](evidence/live-20261017/summary.json).

`account_broker.py`, `live_probe.py` and `test_account_broker.py` implement this
bounded validation. They are not yet wired into Harbor or qualified for unattended
long-term service. The fake-only prototype and its original evidence below remain
unchanged.

## Historical offline feasibility

Result: **OFFLINE_COMPATIBILITY_PASSED; LIVE_NOT_VALIDATED**.

Codex CLI 0.162.1 can remain in native ChatGPT account mode while the coding
container holds only a disposable session placeholder. A separate trusted broker
replaces that placeholder with the upstream account credential. The existing
native coding tools continue to work. This proof uses synthetic credentials and
an entirely local Responses fixture: no real auth.json was read, no API Key was
used, and no real model or B/C Trial ran.

## Smallest promising integration

Keep the native Codex process and tools in the existing Pilot candidate container.
Move only credential custody and request authentication into a separate trusted
process/container, without any candidate code execution there. The upstream
authentication remains the existing Codex/ChatGPT account credential, not Platform
API Key authentication or billing.

The candidate receives a temporary auth.json identifying ChatGPT mode, with a
session-scoped opaque placeholder rather than the upstream access/refresh tokens.
The trusted process sends the real account Authorization and account-ID headers
only to the fixed Codex backend. It must never return or forward real credentials
to candidate code. A stolen temporary placeholder can still invoke permitted
requests during its lifetime; enforce expiry, revocation, quotas and isolation.

The minimal candidate configuration uses a custom provider with
`requires_openai_auth = true`, `wire_api = "responses"` and the broker's explicit
Codex-compatible base URL. The observed login status was **Logged in using
ChatGPT**. Merely changing `chatgpt_base_url` failed on this version because native
workspace-route discovery queried account endpoints before starting inference.

Expected integration changes, not yet applied:

1. A trusted per-Trial broker lifecycle with fixed upstream, bounded requests,
   server-side credential loading and refresh handling, fail-closed expiry and
   cleanup. Never expose a credential-reading or generic proxy endpoint.
2. A narrow Harbor adapter/config overlay supplying the temporary placeholder and
   broker provider config instead of uploading the user's auth.json. Existing
   source collection and the separate verifier remain unchanged.
3. New provenance and appropriate security/transport qualification before B/C.
   A would remain a historical run on the old auth route; disclose that confound.

This is smaller than moving the complete Agent harness to the host. The separate
pre-existing `runtime/agent_colima_report.md` records an App Server/remote-executor
prototype with unresolved extra-tool restrictions. Those unrelated files were
read for comparison and left unchanged. This probe neither enables that route nor
introduces a replacement coding runner.

## What actually passed

The definitive run is `evidence/probe-05/`. Both containers used the image rebuilt
from the frozen Pilot public task and pinned Codex bundle. The upstream fixture
and broker ran in a container distinct from the candidate; Docker used an internal
network with no public egress, no host mounts, separate process namespaces,
non-root UID 1000, read-only roots, all capabilities dropped, no-new-privileges,
bounded memory/CPU/processes and tmpfs storage.

- Native ChatGPT login mode; no API Key field/value used for authentication.
- Nine deterministic Responses requests; account-header replacement verified on
  the trusted side, with the candidate nonce not forwarded upstream.
- Real Codex handlers performed shell reads/search, apply_patch, Python 3.8.20,
  pinned-dependency checks, a harmless source edit and temporary test, serial and
  xdist reproduction commands, PTY continuation and preservation of exit code 7.
- Candidate checks could not see broker credential/state files, broker processes,
  host auth path or Docker socket. Synthetic upstream credential did not occur in
  candidate tool output or Codex logs. File hashes were recorded for mutable
  candidate areas; this is not a claim of a new whole-filesystem B/C leakage audit.
- Six rejection cases: wrong nonce 401, credential-reading endpoint 404,
  arbitrary route 404, unapproved model 403, encoded body 400, oversized body 413.
- After revocation, a request with the formerly valid session nonce returned 401.
- Both containers and the internal network were removed successfully.

The two public reproduction tests intentionally fail on the unfixed source. Their
expected failures are a plumbing check, not a model score. The fixture directs
tool calls; these are not autonomous model reasoning or coding results.

## Limits: do not use this prototype with real authentication

`offline_broker.py` is deliberately hard-wired to a local fixture and asserts a
synthetic credential prefix. `probe.py` has no auth-file, live-provider or real
upstream option. It is not a production credential broker and is not an alternative
command for the previously rejected main-account injection.

The probe does not validate the real Codex service accepting brokered account
headers, token expiry/refresh, account workspace routing, WebSocket support,
compression, concurrent quotas, TLS, crash recovery or an exact monetary cap.
The minimal fixture rejects model-catalog GETs with 404; Codex completes using its
fallback catalog. A live broker must support the approved catalog route and verify
the intended model rather than rely on that fallback. The candidate-to-broker
transport here is HTTP on an isolated local Docker network; live deployment needs
an explicitly reviewed transport boundary. The live trusted service should avoid
shipping the public task payload used in this convenient offline test image.

No claim is made that these checks eliminate every side channel or guarantee
approval. Full account authentication and the actual final authority boundary
still need a separately reviewed, minimal synthetic live check after implementation.
Do not start B/C under this prototype.

## Attempts and preservation

- probe-01: historical A temporary image absent from Docker cache; no container.
- probe-02: Docker cp could not populate tmpfs behind a read-only root; two
  containers and network removed. Replaced cp with bounded trusted stdin upload;
  did not relax the root filesystem restriction.
- probe-03: native account mode recognized, but simple base-URL override failed
  workspace-route discovery; no actual model call. Containers/network removed.
- probe-04: explicit ChatGPT gateway provider passed the native coding sequence.
- probe-05: same successful route plus negative authorization and revocation tests.

Raw records and synthetic credential files stay ignored under `raw/`. Selected
results and their hashes are under `evidence/`. The successful run also preserves
the exact probe source snapshots. No original Eval, Oracle, grader, B/C prompt,
frozen manifest, shared Pilot/Runtime, prior evidence or main-account file changed.
No push performed.

## References

- [ChatGPT through a gateway](https://learn.chatgpt.com/docs/enterprise/sign-in-with-chatgpt-through-a-gateway): native account auth provider/header semantics. The
  documented gateway alone still gives Codex its credential; the separate-custody
  placeholder broker is our tested offline proposal, not an official feature claim.
- [Codex authentication](https://learn.chatgpt.com/docs/auth): account login/storage.
- Local installed Harbor 0.24.0 Codex adapter and native 0.162.1 CLI help were used
  to check behavior against the versions in this repository.
