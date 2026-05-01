import os
from asyncio import run

from contree_sdk import Contree


async def main():
    # Get client
    client = Contree()

    # Get images (to verify that connection works)
    await client.images()


if __name__ == "__main__":
    token = os.getenv("NEBIUS_API_KEY")
    if not token:
        os.environ["NEBIUS_API_KEY"] = input("Please enter Nebius IAM token: ")
    run(main())
