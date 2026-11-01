# Harbor dataset E2E tests

These tests run real Oracle trials on ConTree. The normal pytest configuration
excludes them, including in CI. Install the test dependencies with Python 3.12+:

```bash
uv sync --extra dev --extra harbor
```

Configure the cluster through `CONTREE_URL`, `CONTREE_TOKEN` (or
`NEBIUS_API_KEY`), and `CONTREE_PROJECT` (or `NEBIUS_AI_PROJECT`). Alternatively,
select a saved profile through `CONTREE_PROFILE`. No Stage endpoint or profile
is hardcoded in the tests. See the
[connection configuration](../../../docs/python_sdk/getting-started.md#connection-sources).

## Run TB2.1

The default sample has ten tasks: seven known passes and three known failures
that may relate to ConTree. Known zero rewards report XFAIL; improvements report
PASS. Harbor exceptions, missing verifier artifacts, and unexpected zero rewards
always fail.

```bash
uv run pytest tests/e2e/harbor/test_tb21.py -m e2e
```

The full suite runs all 87 tasks in the pinned dataset except `compile-compcert`
and `caffe-cifar-10`. Every task must earn reward 1. Reproducing the recorded
results gives 79 PASS and eight FAIL; those failures remain visible for investigation.

```bash
uv run pytest tests/e2e/harbor/test_tb21.py -m e2e --harbor-suite=full --harbor-workers=50
```

Agents can select one task without running the rest:

```bash
uv run pytest tests/e2e/harbor/test_tb21.py -m e2e --harbor-suite=full -k gpt2-codegolf
```

Harbor runs the selected tasks in one job, with ten workers by default, one
attempt per task, and no retries. Use `--harbor-workers=N` for concurrency;
pytest-xdist is not needed. Task images, commands, and verifiers are unchanged.

Artifacts persist under `_tmp/harbor-e2e/<job-name>/`, including the resolved
configuration, task locks, trial results, Oracle output, and verifier output.
Failures and XFAILs include the trial artifact path. Set
`--harbor-jobs-dir=PATH` to use another directory.

## Add another dataset

Add a module next to `test_tb21.py`. Provide a module-scoped `harbor_dataset`
fixture returning Harbor's `DatasetConfig`, pin its dataset reference, and
parametrize `task_name` for the sample or full suite. The shared `harbor_results`
fixture runs only selected pytest cases and returns their `TrialResult` objects
by task name. Keep dataset-specific assertions and known failure diagnoses in
that module.
