from asyncio import run

from contree_client.asyncio import ContreeAsyncClient
from contree_client.types import ContreeAsyncClient as ContreeAsyncClientBase


async def main(client: ContreeAsyncClientBase, image_uuid: str):
    await client.update_image_tag(image_uuid, "my-custom-tag:v1")
    print(f"Tagged {image_uuid} as my-custom-tag:v1")

    resolved = await client.resolve_image("tag:my-custom-tag:v1")
    print(f"Resolves back to: {resolved=}")

    await client.delete_image_tag(image_uuid, tag="my-custom-tag:v1")
    print("Tag removed")


async def run_with_first_tagged_image() -> None:
    client = ContreeAsyncClient.from_profile()
    images = await client.list_images(tagged=True, limit=1)
    image_uuid = images.images[0].uuid
    if not isinstance(image_uuid, str):
        raise TypeError("expected image uuid in list_images response")
    await main(client=client, image_uuid=image_uuid)


if __name__ == "__main__":
    run(run_with_first_tagged_image())
