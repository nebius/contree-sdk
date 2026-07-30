import asyncio
import os

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from contree_sdk import Contree
from contree_sdk.langchain.sandbox import ContreeSandbox


async def main():
    client = Contree()
    image = await client.images.oci("python:3.13-slim")
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


if __name__ == "__main__":
    asyncio.run(main())
