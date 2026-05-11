from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.extra.contree import ContreeEnvironment
from minisweagent.models import get_model

from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig


def main():
    contree_env = ContreeEnvironment(
        contree_config=ContreeConfig(
            auth=IAMAuth(base_url="https://contree.dev/"),
        ),
        image="python:3.13-slim",
        cwd="/workspace",
    )

    agent = DefaultAgent(
        get_model(input_model_name="gemini/gemini-flash-latest"), contree_env, system_template="", instance_template=""
    )
    agent.run("Develop small calculator script and check it")

    result = contree_env.session.run(shell="ls /workspace -lah").wait()
    print(result.stdout)


if __name__ == "__main__":
    main()
