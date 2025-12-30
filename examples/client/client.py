import os
from asyncio import run

from contree_sdk import Contree


async def main(token: str):
    # Get client
    client = Contree(token=token)

    # Get images (to verify that connection works)
    await client.images()


if __name__ == "__main__":
    token = os.getenv("CONTREE_TOKEN")
    if not token:
        token = input("Please enter contree token: ")
    run(main(token=token))
