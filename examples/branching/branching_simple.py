from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    base = await sdk.images.use("alpine:latest")

    child = await base.run(shell='echo "$RANDOM" > /tmp/random.txt', disposable=False)
    print(f"Child created from base, UUID: {child.uuid}\n")

    for i, letter in enumerate(["A", "B", "C"], 1):
        gc = await child.run(
            shell=f"echo '{letter}' >> /tmp/random.txt && cat /tmp/random.txt",
            disposable=False,
        )
        print(f"Grandchild {i}: {gc.stdout.strip()}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
