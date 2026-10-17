## Execution and submission

The workspace root is `/work`. Python 3.8.20 and pinned dependencies are already
installed, including pytest-xdist 1.29.0. Use the provided `python`; do not change
dependencies or configuration.

Existing repository tests are in `testing/`. Public reproduction examples are in
`eval_public/test_example.py`. These examples intentionally fail; their exit
status may remain nonzero after the reporting defect is fixed. From `/work`:

```sh
PYTHONPATH=/work/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q eval_public/test_example.py
PYTHONPATH=/work/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p xdist.plugin -n 1 eval_public/test_example.py
```

Use the same environment variables with other tests you choose to run. You may
create temporary debugging tests. The submitted patch may contain only UTF-8
Python source changes under `src/`, excluding `src/_pytest/_version.py`. New Python
helpers under `src/` are allowed. Do not submit changes to tests, dependencies or
configuration, binary files, renames, symlinks or executable modes.

For new source files, use `git add -N src/path_to_new_file.py`, then collect:

```sh
git diff --binary HEAD -- src/ > /work/submission.patch
```

Submit the source changes; a written explanation alone is not a submission.
The Agent time budget is 1800 seconds. Resources: 2 CPU cores, 4 GiB RAM,
128 processes, a 1536 MiB workspace, 256 MiB temporary storage, 64 MiB HOME,
128 MiB logs, and a 32 MiB individual file limit. Independent verification is
performed afterward with a separate 1800-second budget.
