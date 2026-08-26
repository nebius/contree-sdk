from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    result = await image.run(shell="echo 'Hello World'")
    print(f"Simple echo: {result.stdout=}, {result.stderr=}, {result.exit_code=}")

    result = await image.run(shell="pwd")
    print(f"Current directory: {result.stdout=}, {result.exit_code=}")

    result = await image.run(shell="ls -la")
    print(f"Directory listing: {result.stdout=}, {result.exit_code=}")

    result = await image.run(shell="cat -", stdin="Hello from stdin\n")
    print(f"Cat with stdin: {result.stdout=}, {result.exit_code=}")

    result = await image.run(shell="echo 'Error message' >&2; exit 1")
    print(f"Error command: {result.stdout=}, {result.stderr=}, {result.exit_code=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
