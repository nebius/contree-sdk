# delete file later
# only for testing and demonstration purposes
from run_client import TOKEN

from contree_sdk.api.client.client import ContreeClient, ContreeSyncClient
from contree_sdk.api.models import ImageKind
from contree_sdk.api.models.image_import import ImageImportRequest, RegistryInfo


async def amain():
    client = ContreeClient(token=TOKEN)

    # import request api
    print("Importing image busybox:latest...")
    import_request = ImageImportRequest(
        registry=RegistryInfo(url="docker://docker.io/busybox:latest"), tag="busybox:latest", timeout=300
    )
    operation_id = await client.start_import_image(import_request)
    print(f"Import operation started with ID: {operation_id}")

    import_status = await client.get_image_import_status(operation_id)
    print(f"Import status: {import_status}")

    # print("Cancelling image busybox:latest...")
    # await client.cancel_image_import(operation_id) # waiting for fixes on server

    old_operation_id = "019a6dc7-9d15-781e-8633-2f59310cb45b"
    print("Old import request status", await client.get_image_import_status(old_operation_id))

    # images API
    images = await client.get_images(kind=ImageKind.IMPORTED)
    print("Images:", images)

    # waiting for fixes on server
    # for image in images:
    #     print("Inspect image files", await client.list_image_files(image.uuid, "/root"))
    #     print("Inspected image:", await client.inspect_image(image.uuid))
    #     break


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
