# delete file later
# only for testing and demonstration purposes
from contree_sdk.client.client import ContreeClient, ContreeSyncClient
from contree_sdk.client.run_client import TOKEN
from contree_sdk.models.image import ImageKind
from contree_sdk.models.image_import import ImageImportRequest, RegistryInfo


async def amain():
    client = ContreeClient(token=TOKEN)

    import_request = ImageImportRequest(
        registry=RegistryInfo(url="docker://docker.io/busybox:latest"), tag="busybox:latest", timeout=300
    )

    print("Importing image busybox:latest...")
    # operation_id = await client.import_image(import_request)
    operation_id = "019a6dc7-9d15-781e-8633-2f59310cb45b"
    print(f"Import operation started with ID: {operation_id}")

    # Check import status
    import_status = await client.get_image_import_status(operation_id)
    print(f"Import status: {import_status}")

    images = await client.get_images(kind=ImageKind.IMPORTED)
    print("Images:", images)

    for image in images:
        print("Inspect image files", await client.list_image_files(image.uuid, "/root"))
        print("Inspected image:", await client.inspect_image(image.uuid))

        print("Checked import status", await client.get_image_import_status(image.uuid))
        break


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
