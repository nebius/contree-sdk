from contree_sdk import Contree


async def main(client: Contree, image_tag: str):
    image = await client.images.use(image_tag, strict=True)
    print(f"Original: {image.uuid=}, {image.tag=}")

    tagged = await image.tag_as("my-custom-tag:v1")
    print(f"After tag_as: {tagged.uuid=}, {tagged.tag=}")

    untagged = await tagged.untag()
    print(f"After untag: {untagged.uuid=}, {untagged.tag=}")

    result = await image.run(shell="echo hello", tag="my-result:v1", disposable=False)
    print(f"Run result: {result.uuid=}, {result.tag=}")


if __name__ == "__main__":
    import asyncio

    async def _run():
        client = Contree()
        images = await client.images(number=1, tagged=True)
        await main(client=client, image_tag=images[0].tag)

    asyncio.run(_run())
