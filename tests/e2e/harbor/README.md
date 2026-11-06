# Harbor dataset E2E tests

Oracle trials on ConTree. Excluded from default test runs and CI.

## Setup

Requires Python 3.12+:

```bash
uv sync --extra dev --extra harbor
```

Set `CONTREE_URL`, `CONTREE_TOKEN` (or `NEBIUS_API_KEY`), and `CONTREE_PROJECT`
(or `NEBIUS_AI_PROJECT`), or select a saved profile with `CONTREE_PROFILE`.
See [connection configuration](../../../docs/python_sdk/getting-started.md#connection-sources).

## Run TB2.1

Sample: ten tasks, with a baseline of seven PASS and three XFAIL.

```bash
uv run pytest tests/e2e/harbor/test_tb21.py -m e2e
```

Full: 87 tasks, excluding `compile-compcert` and `caffe-cifar-10`.
Baseline: 79 PASS and eight XFAIL.

```bash
uv run pytest tests/e2e/harbor/test_tb21.py -m e2e --harbor-suite=full --harbor-workers=50
```

Single task:

```bash
uv run pytest tests/e2e/harbor/test_tb21.py -m e2e --harbor-suite=full -k gpt2-codegolf
```

Both modes use the same baseline checks. Known zero rewards are XFAIL.
Unexpected zero rewards, Harbor exceptions, and missing artifacts fail.
A known failure that passes also fails: review the result and update
`KNOWN_FAILURES` to acknowledge the improvement. Error details are not matched.

Each invocation runs one Harbor job: ten workers by default, one attempt per
task, no retries. Set concurrency with `--harbor-workers=N`.

Artifacts: `_tmp/harbor-e2e/<job-name>/`. Override with `--harbor-jobs-dir=PATH`.
FAIL and XFAIL messages include the trial artifact path.

## Add another dataset

Add a module with a module-scoped `harbor_dataset` fixture returning a pinned
`DatasetConfig` and parametrize `task_name`. The shared `harbor_results` fixture
runs selected tasks and returns `TrialResult` objects keyed by task name.
Keep assertions and the failure baseline in the dataset module.
