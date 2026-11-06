from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest


if TYPE_CHECKING:
    from harbor.models.job.config import DatasetConfig
    from harbor.models.trial.result import TrialResult


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("Harbor E2E")
    group.addoption("--harbor-suite", choices=["sample", "full"], default="sample")
    group.addoption("--harbor-workers", type=int, default=10, help="Concurrent Harbor trials")
    group.addoption("--harbor-jobs-dir", default="_tmp/harbor-e2e", help="Retained Harbor run artifacts")


@pytest.fixture(scope="module")
async def harbor_results(
    harbor_dataset: DatasetConfig, request: pytest.FixtureRequest, pytestconfig: pytest.Config
) -> dict[str, TrialResult]:
    from harbor.job import Job
    from harbor.models.job.config import JobConfig, RetryConfig
    from harbor.models.trial.config import AgentConfig, EnvironmentConfig

    selected = [
        item.callspec.params["task_name"]
        for item in request.session.items
        if isinstance(item, pytest.Function) and item.module is request.module
    ]
    workers = pytestconfig.getoption("harbor_workers")
    if workers < 1:
        raise pytest.UsageError("--harbor-workers must be positive")
    dataset = harbor_dataset.model_copy(update={"task_names": [f"*/{name}" for name in selected]})
    config = JobConfig(
        job_name=f"{request.module.__name__.rsplit('.', 1)[-1]}-{uuid4().hex[:12]}",
        jobs_dir=Path(pytestconfig.getoption("harbor_jobs_dir")),
        n_concurrent_trials=workers,
        n_attempts=1,
        retry=RetryConfig(max_retries=0),
        agents=[AgentConfig(name="oracle")],
        environment=EnvironmentConfig(import_path="contree_sdk.harbor:ConTreeEnvironment"),
        datasets=[dataset],
        quiet=True,
    )
    job = await Job.create(config)
    logging.getLogger(__name__).info("Harbor E2E artifacts: %s", job.job_dir.resolve())
    result = await job.run()
    if result.finished_at is None:
        pytest.fail(f"Harbor job did not finish: {job.job_dir}")
    if result.n_total_trials != len(selected):
        pytest.fail(f"Unexpected trial count: {job.job_dir}")
    if len(result.trial_results) != len(selected):
        pytest.fail(f"Missing trial results: {job.job_dir}")
    results = {trial.task_name.rsplit("/", 1)[-1]: trial for trial in result.trial_results}
    if set(results) != set(selected):
        pytest.fail(f"Unexpected tasks: {job.job_dir}")
    return results
