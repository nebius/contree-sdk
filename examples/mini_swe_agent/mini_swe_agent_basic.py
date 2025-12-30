from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.extra.contree import ContreeEnvironment
from minisweagent.models.litellm_model import LitellmModel

from contree_sdk.config import ContreeConfig


def main():
    model = LitellmModel(model_name="gemini/gemini-flash-latest")

    contree_env = ContreeEnvironment(
        contree_config=ContreeConfig(
            token="your-contree-token",
            base_url="https://your-contree-instance.com",
        ),
        image="ubuntu:focal",
        cwd="/workspace",
    )

    agent = DefaultAgent(model, contree_env)
    agent.run("Develop small calculator script and check it")

    result = contree_env.session.run(shell="ls /workspace -lah").wait()
    print(result.stdout)


if __name__ == "__main__":
    main()
