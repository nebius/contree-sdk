import os
from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient) -> None:
    sdk = Contree(api_client)

    # Get images (to verify that connection works)
    await sdk.images()


async def run_example() -> None:
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The API client owns resources; Contree creates only cheap SDK objects.
    async with DefaultContreeAsyncClient(os.environ["NEBIUS_API_KEY"]) as api_client:
        await main(api_client)


if __name__ == "__main__":
    token = os.getenv("NEBIUS_API_KEY")
    if not token:
        os.environ["NEBIUS_API_KEY"] = input("Please enter Nebius IAM token: ")
    run(run_example())
