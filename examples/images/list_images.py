from asyncio import run
from datetime import datetime, timedelta

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    all_images = await sdk.images()
    print(f"Loaded {all_images=}")

    limited_images = await sdk.images(number=3)
    print(f"Found {len(limited_images)=}")

    tagged_images = await sdk.images(tagged=True)
    print(f"Found {len(tagged_images)=}")

    recent_images = await sdk.images(since=datetime.now() - timedelta(days=7), number=5)
    print(f"Found {len(recent_images)=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
