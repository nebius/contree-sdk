from textwrap import dedent

import pytest


pytest.importorskip("harbor")

from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig, TrialConfig
from harbor.trial.trial import Trial


async def test_dockerfile_oracle_trial(tmp_path, monkeypatch, record_property):
    task_dir = tmp_path / "sort-with-dockerfile"
    files = {
        "task.toml": """
            [environment]
            build_timeout_sec = 180.0
            cpus = 1
            memory_mb = 512

            [agent]
            timeout_sec = 60.0

            [verifier]
            timeout_sec = 60.0
        """,
        "instruction.md": "Sort /app/input.txt alphabetically and save the lines to /app/result.txt.\n",
        "environment/Dockerfile": """
            FROM ubuntu:24.04
            COPY input.txt /app/input.txt
            RUN LC_ALL=C sort /app/input.txt > /app/built.txt
        """,
        "environment/input.txt": "pear\napple\nbanana\n",
        "solution/solve.sh": """
            #!/bin/bash
            set -eu
            LC_ALL=C sort /app/input.txt > /app/result.txt
        """,
        "tests/test.sh": """
            #!/bin/bash
            set -eu
            reward=0
            if printf 'apple\\nbanana\\npear\\n' | cmp -s - /app/built.txt \
                && cmp -s /app/built.txt /app/result.txt; then
                reward=1
            fi
            printf '%s\\n' "$reward" > /logs/verifier/reward.txt
        """,
    }
    for name, content in files.items():
        path = task_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content).lstrip(), encoding="utf-8", newline="\n")

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    config = TrialConfig(
        task=TaskConfig(path=task_dir),
        agent=AgentConfig(name="oracle"),
        environment=EnvironmentConfig(import_path="contree_sdk.harbor:ConTreeEnvironment"),
        trials_dir=tmp_path / "trials",
        trial_name="dockerfile",
    )
    artifacts = config.trials_dir / config.trial_name
    record_property("harbor_artifacts", str(artifacts))
    trial = await Trial.create(config)
    result = await trial.run()

    assert result.exception_info is None, f"{result.exception_info}\nArtifacts: {artifacts}"
    assert result.verifier_result is not None, f"No verifier result: {artifacts}"
    assert result.verifier_result.rewards == {"reward": 1.0}, f"Artifacts: {artifacts}"
