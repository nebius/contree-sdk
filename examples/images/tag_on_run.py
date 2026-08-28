from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    contree = Contree(api_client)
    image = await contree.images.use("ubuntu:latest")
    result = await image.run(shell="pip install mylib && python setup.py", tag="myapp:ready", disposable=False)
    print(result.tag)  # "myapp:ready"


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
