import asyncio
import os

from contree_client.sync import ContreeClient
from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from contree_sdk.langchain import ContreeSandbox
from contree_sdk.session import ContreeSession


async def main():
    client = ContreeClient.from_profile()
    session = ContreeSession(client, image="tag:python:3.13-slim")
    sandbox = ContreeSandbox(session=session)

    model = ChatOpenAI(
        model="zai-org/GLM-5.2",
        base_url="https://api.studio.nebius.ai/v1/",
        api_key=SecretStr(os.environ["NEBIUS_API_KEY"]),
    )

    agent = create_deep_agent(model=model, backend=sandbox)
    result = await agent.ainvoke({"messages": [HumanMessage("Develop a small calculator script and run it")]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
