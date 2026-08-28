import asyncio
import os

from contree_client.base import ContreeAsyncClient
from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from contree_sdk import Contree
from contree_sdk.langchain.sandbox import ContreeSandbox


async def main(api_client: ContreeAsyncClient) -> None:
    sdk = Contree(api_client)
    image = await sdk.images.oci("python:3.13-slim")
    session = image.session()
    sandbox = ContreeSandbox(session=session)

    model = ChatOpenAI(
        model="zai-org/GLM-5.2",
        base_url="https://api.studio.nebius.ai/v1/",
        api_key=SecretStr(os.environ["NEBIUS_API_KEY"]),
    )

    agent = create_deep_agent(model=model, backend=sandbox)
    result = await agent.ainvoke({"messages": [HumanMessage("Develop a small calculator script and run it")]})
    print(result["messages"][-1].content)


async def run_example() -> None:
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The API client owns resources; Contree creates only cheap SDK objects.
    async with DefaultContreeAsyncClient(os.environ["NEBIUS_API_KEY"]) as api_client:
        await main(api_client)


if __name__ == "__main__":
    asyncio.run(run_example())
