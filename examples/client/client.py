import os
from asyncio import run

from contree_client.httpx import ContreeAsyncClient

from contree_sdk import Contree


async def main():
    # Build the transport: contree_sdk performs no I/O of its own, the
    # caller owns auth/retries/base_url via the injected contree_client backend.
    api = ContreeAsyncClient(os.environ["NEBIUS_API_KEY"])
    client = Contree(api)

    # Get images (to verify that connection works)
    await client.images()


if __name__ == "__main__":
    token = os.getenv("NEBIUS_API_KEY")
    if not token:
        os.environ["NEBIUS_API_KEY"] = input("Please enter Nebius IAM token: ")
    run(main())
