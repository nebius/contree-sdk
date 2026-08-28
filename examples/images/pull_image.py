from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    images = await sdk.images(number=1)
    tagged_images = await sdk.images(number=1, tagged=True)
    image_uuid = images[0].uuid
    image_tag = tagged_images[0].tag
    if image_uuid is None or image_tag is None:
        raise RuntimeError("The selected images must have a UUID and tag")

    print(f"Selected {image_uuid=}")
    print(f"Selected {image_tag=}")

    print("\nPulling by UUID (strict):")
    result = await sdk.images.use(image_uuid, strict=True)
    print(f"Pulled by UUID: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nPulling by tag (strict):")
    result = await sdk.images.use(image_tag, strict=True)
    print(f"Pulled by tag: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nImporting public image using oci:")
    result = await sdk.images.oci("docker://ghcr.io/linuxserver/code-server:latest")
    print(f"Pulled public: {result.uuid=}, {result.tag=}, {result.state=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
