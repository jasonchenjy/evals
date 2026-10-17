# Harbor replacement spike

The supervised real-Eval pilot implementation and security gates are documented
in [pilot/README.md](pilot/README.md), with actual outcomes and the incomplete
real trial documented in [PILOT_REPORT.md](PILOT_REPORT.md). The earlier commands below retain their
original trusted-control scope and machine-specific configuration.

All integration code, generated contexts, isolated dependencies and evidence live here. Do not edit `../runtime` or `../pytest_5786`. No push is authorized.

## Setup

Host: macOS arm64, Python 3.13 controller, existing Colima Docker Engine 29.2.1. Harbor 0.24.0 (installed PyPI wheel, recorded in evidence/installed-harbor.json) requires Python >=3.12; candidate/grader retain Python 3.8.20. `sh harbor/setup.sh` installs only in `harbor/.venv` and `harbor/tools`. Compose 5.6.0 is verified against the official release SHA256. No Docker Desktop policy or global Docker configuration is changed.

The launcher uses the existing socket `unix:///Users/junyu/.colima/default/docker.sock` and task-local Docker config/HOME. It requires the already-provisioned `pytest5786-runtime:py3820` image, identity `sha256:1734efd60ea49a9bef74be6943cf0845625048f2ba59b36461fdb78a3f8cc9a9`. This reuse does not import runtime Python code. The image contains Python 3.8.20 and pinned Eval dependencies. For another machine, provision the same image and update the socket deliberately; requalify before claiming equivalence.

## Synthetic qualification

`python3.13 harbor/launch.py spike --output harbor/raw/spike-001`

This creates three real Harbor `Trial` instances through a custom `BaseAgent` adapter. Task interface is `task.toml`, `instruction.md`, `environment/Dockerfile`, and `tests/test.sh`. Explicit `environment_mode="separate"` forces a fresh verifier, rather than the default shared verification. Only declared source artifacts and small environment observations transfer. The fresh verifier checks the original fixed synthetic Git base, hidden-test absence observation and distinct hostnames, then records a source diff, checks, result.json and reward.json. Correct negative outcomes have reward 0; infrastructure errors are never counted as expected failures.

Generated task contexts and raw logs are ignored. Curated execution records are under `evidence/`. See `REPORT.md` for actual outcomes and security limitations.

## Interface references

- [Harbor official repository](https://github.com/harbor-framework/harbor), inspected commit `f2c1be516df1995bea0bffd224169c8e8faa6a04`, project version 0.24.0.
- [Separate verifier](https://harborframework.com/docs/tasks/separate-verifier): dedicated container; artifacts restored at original source paths, not host destination paths.
- Installed source: `harbor.models.task.config.VerifierConfig`, `harbor.trial.trial.Trial`, `harbor.trial.artifact_handler.ArtifactHandler`, `harbor.agents.installed.codex.Codex`.
- [Codex authentication](https://developers.openai.com/codex/auth): supported API key/ChatGPT login. Harbor supports `OPENAI_API_KEY` or explicit `CODEX_AUTH_JSON_PATH`/`CODEX_FORCE_AUTH_JSON`. Its built-in adapter copies selected auth.json into the agent container. This integration must not enable that route without explicit approval.

## Colima compatibility

This daemon cannot see host `/Users/junyu/...` paths: a read-only Docker bind probe returned `bind source path does not exist`. Stock Harbor Docker advertises `mounted=True`, so it expected reward files through log binds and returned RewardFileNotFoundError. `colima.py` is a small custom Environment adapter via Harbor's supported `import_path`: it removes only known Harbor log binds, rejects other host mounts, creates log directories and advertises `mounted=False`. Harbor then uses its existing cp/upload/download protocol for both environments. No installed Harbor code, Docker policy or VM configuration was changed.

Harbor also requires Buildx to build the network policy sidecar. The task-local Buildx 0.38.0 plugin is extracted from a SHA256-verified official Homebrew bottle by `setup_buildx.py`; Compose 5.6.0 remains task-local. The initial direct Buildx download repeatedly timed out. Controller dependencies are frozen in `requirements-controller.lock`.

## pytest_5786

```
python3.13 -B harbor/pytest_5786/build.py
python3.13 harbor/launch.py pytest_5786 --output harbor/raw/pytest-new
python3.13 harbor/compare.py harbor/raw/pytest-new
```

`build.py` verifies the original lock, calls unchanged prepare.export(), copies the exact instruction, creates task.toml and builds a dedicated verifier context. The original package remains the single source of truth. Generated contexts contain only transient inputs required by the original grader's integrity check and are ignored by Git. The grader requires its locked oracle files to exist; these remain absent from the Agent environment but are present in the verifier. This is an explicit security limitation for hostile candidate code, not a scoring change.

`verify.py` accepts only regular Python source with baseline execute bits (new files cannot be executable), protects the version shim, creates a diff against the trusted fresh synthetic index and calls the original grader. The original grader creates another fresh snapshot of commit 955e54221008aba577ecbaefa15679f6777d3bf8, checks Python 3.8.20 and every pinned dependency, validates/applies the diff and returns unchanged dimensions/checks. reward.json adds overall reward and four 0/1 dimensions. Original detailed grader results are preserved. H02 remains diagnostic-only.

## Real Codex synthetic trial

```
python3.13 harbor/spike/prepare_codex.py
python3.13 harbor/launch.py codex-spike --output harbor/raw/codex-new
```

The preparation script copies only a preprovisioned Linux arm64 CLI vendor directory, never authentication. The recorded run used Codex 0.162.1 and openai/gpt-6.1-sol. The run command selects explicit auth.json authentication and is documented for review/reproduction only: the user authorized exactly one synthetic trial in this session, which has completed. Do not run another authenticated trial under that authorization. Review and authorize credentials afresh before any future run. The built-in adapter uploads auth only at runtime, archives sessions/ATIF trace and removes its temporary CODEX_HOME/secrets; Harbor then destroys the container. The verifier uses the original credential-free task image. No real pytest_5786 Agent trial is authorized by the synthetic-only credential grant.

## Evidence

`python3.13 harbor/curate.py harbor/raw/<run> --name <new-evidence-name>` copies selected results, patches and logs, excludes workspaces/artifact source trees/auth files, scans credential patterns and writes a SHA256 manifest. Raw attempts stay local; failure summaries and logs are retained as well. A code reward of 0 requires successful grading; missing rewards and exceptions are infrastructure failures.

Final executed qualification: `harbor/raw/pytest-003`; curated final results: `evidence/pytest_5786-final/summary.json`; full comparison: `evidence/qualification-comparison.json`. All 7 expectations and 91 reference statuses match. See REPORT.md for the migration decision.
