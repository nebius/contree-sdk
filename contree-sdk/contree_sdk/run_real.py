# delete file later
# only for testing and demonstration purposes
from contree_sdk.client.client import ContreeClient, ContreeSyncClient
from contree_sdk.client.run_client import TOKEN
from contree_sdk.models.image import ImageKind


async def amain():
    client = ContreeClient(token=TOKEN)
    images = await client.get_images(kind=ImageKind.IMPORTED)
    print("Images:", images)
    for image in images:
        print("Inspected image:", await client.inspect_image(image.uuid))


def main():
    client = ContreeSyncClient(token=TOKEN)

    images = client.get_images(kind=ImageKind.IMPORTED)
    print("Images:", images)
    for image in images:
        print("Inspected image:", client.inspect_image(image.uuid))


if __name__ == "__main__":
    import asyncio

    asyncio.run(amain())

    main()
