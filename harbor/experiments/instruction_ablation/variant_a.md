# Preserve chained exception reporting in distributed pytest runs

Running the same failing tests locally and with pytest-xdist produces different error information. Locally, pytest shows the earlier exceptions and how they led to the final failure. With distributed execution, only the last exception is displayed. This occurs both with explicit `raise ... from ...` causes and with exceptions raised while handling another exception.

For example, a test that raises ValueError(11), then ValueError(12) from that exception, then ValueError(13) from the second exception should report all three failures and their causal relationships. Distributed execution should retain the useful error information available in the corresponding local run.

Inspect the repository and implement a working source-code fix. Preserve pytest's established report behavior, including failures during test collection, captured output and attached report sections, normal single-exception reporting, and Python's rules about which exception context is displayed. Reports must remain usable by their existing consumers; fixing only the visible example is insufficient. Continue to support valid exception objects and the representations already produced by this version of pytest.

You may inspect the base repository, edit Python source under `src/`, and run its public tests or add your own local debugging tests. The provided `eval_public/test_example.py` intentionally fails and reproduces the reported symptom; compare a local run with `-p xdist.plugin -n 1`. A failing test's expected exit status is still nonzero after the reporting defect is fixed.

Submit a UTF-8 Git unified diff against the supplied baseline. Include only Python source changes under `src/`; do not modify the generated `src/_pytest/_version.py`, dependencies, configuration, or existing tests in the submitted patch. New Python source helpers under `src/` are allowed. A written explanation alone is not a submission.

The runtime provides Python 3.8.20 and pinned dependencies, including pytest-xdist 1.29.0. No network is needed during the trial. Use the runtime's Python executable with `PYTHONPATH` pointing to this workspace's `src` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`; enable xdist explicitly when using it. Useful public commands from the workspace root:

```sh
python -m pytest -q eval_public/test_example.py
python -m pytest -q -p xdist.plugin -n 1 eval_public/test_example.py
python -m pytest -q testing/test_reports.py testing/code/test_code.py testing/code/test_excinfo.py
git diff --binary HEAD -- src/ > submission.patch
```

For new source files, stage them with `git add -N src/path_to_new_file.py` before collecting the diff. Follow the runtime's time and resource limits.
