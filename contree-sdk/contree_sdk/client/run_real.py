# delete file later
# only for testing and demonstration purposes
from contree_sdk.client.client import ContreeClient, ContreeSyncClient
from contree_sdk.client.run_client import TOKEN


async def amain():
    client = ContreeClient(token=TOKEN)
    print(await client.get_images())


def main():
    client = ContreeSyncClient(token=TOKEN)
    print(client.get_images())


if __name__ == "__main__":
    import asyncio

    asyncio.run(amain())

    main()
