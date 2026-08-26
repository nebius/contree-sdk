from asyncio import run

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    images = await sdk.images(number=1, tagged=True)
    image_tag = images[0].tag
    if image_tag is None:
        raise RuntimeError("The selected image must have a tag")

    image = await sdk.images.use(image_tag, strict=True)
    print(f"Original: {image.uuid=}, {image.tag=}")

    tagged = await image.tag_as("my-custom-tag:v1")
    print(f"After tag_as: {tagged.uuid=}, {tagged.tag=}")

    untagged = await tagged.untag()
    print(f"After untag: {untagged.uuid=}, {untagged.tag=}")

    result = await image.run(shell="echo hello", tag="my-result:v1", disposable=False)
    print(f"Run result: {result.uuid=}, {result.tag=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
