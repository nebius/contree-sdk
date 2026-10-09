import sys
from pathlib import Path

import pytest


if sys.version_info < (3, 12):
    pytest.skip("Harbor requires Python 3.12+", allow_module_level=True)
pytest.importorskip("harbor")
pytest.importorskip("httpx")

from harbor.agents.oracle import OracleAgent
from harbor.models.agent.context import AgentContext
from harbor.models.task.task import Task
from harbor.models.trial.paths import TrialPaths

from contree_sdk.harbor import ConTreeEnvironment


async def test_harbor_oracle(contree, tmp_path):
    task_dir = Path(__file__).resolve().parents[3] / "examples" / "harbor"
    task = Task(task_dir)
    paths = TrialPaths(trial_dir=tmp_path / "trial")
    paths.mkdir()
    environment = ConTreeEnvironment(
        environment_dir=task.paths.environment_dir,
        environment_name="contree/hello-world",
        session_id="contree-oracle-test",
        trial_paths=paths,
        task_env_config=task.config.environment,
        client=contree,
    )
    agent = OracleAgent(logs_dir=paths.agent_dir, task_dir=task_dir, trial_paths=paths)
    try:
        await environment.start(force_build=False)
        await agent.setup(environment)
        await agent.run(task.instruction, environment, AgentContext())
        await environment.upload_dir(task.paths.tests_dir, "/tests")
        result = await environment.exec("bash /tests/test.sh", timeout_sec=60, user="root")
        assert result.return_code == 0
        await environment.download_dir("/logs/verifier", paths.verifier_dir)
        assert paths.reward_text_path.read_text().strip() == "1"
        assert (paths.agent_dir / "oracle.txt").is_file()
    finally:
        await environment.stop(delete=True)
