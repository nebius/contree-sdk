from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    contree = Contree(api_client)
    image = await contree.images.use("busybox:latest")

    prepared = await image.run(
        shell="true",
        env={"MY_PERSISTED_VAR": "persisted_value"},
        preserve_env=True,
        disposable=False,
    )
    result = await prepared.run("/bin/printenv", args=["MY_PERSISTED_VAR"])
    print(result.stdout)


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
