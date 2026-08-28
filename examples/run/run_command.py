from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("alpine:3.20", strict=True)
    print(f"Pulled {image=}")

    print("\nExample 1: Simple command execution")
    result = await image.run("/bin/echo", args=["Hello from command parameter!"])
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: Command with arguments")
    result = await image.run("/bin/ls", args=["-la", "/tmp"])
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 3: Command with environment variables")
    result = await image.run("/bin/printenv", args=["MY_VAR"], env={"MY_VAR": "test_value"})
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 4: Preserve environment variables in the resulting image")
    prepared = await image.run(
        shell="true",
        env={"MY_PERSISTED_VAR": "persisted_value"},
        preserve_env=True,
        disposable=False,
    )
    result = await prepared.run("/bin/printenv", args=["MY_PERSISTED_VAR"])
    print(f"Result: {result.stdout=}, {result.exit_code=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
