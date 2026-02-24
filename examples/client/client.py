import os
from asyncio import run

from contree_sdk import Contree


async def main():
    # Get client
    client = Contree()

    # Get images (to verify that connection works)
    await client.images()


if __name__ == "__main__":
    token = os.getenv("CONTREE_TOKEN")
    if not token:
        os.environ["CONTREE_TOKEN"] = input("Please enter contree token: ")
    run(main())
