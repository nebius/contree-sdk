from contree_sdk import ContreeSync


def main(client: ContreeSync, image_tag: str):
    image = client.images.use(image_tag, strict=True)
    print(f"Original: {image.uuid=}, {image.tag=}")

    tagged = image.tag_as("my-custom-tag:v1")
    print(f"After tag_as: {tagged.uuid=}, {tagged.tag=}")

    untagged = tagged.untag()
    print(f"After untag: {untagged.uuid=}, {untagged.tag=}")

    result = image.run(shell="echo hello", tag="my-result:v1", disposable=False).wait()
    print(f"Run result: {result.uuid=}, {result.tag=}")


if __name__ == "__main__":
    client = ContreeSync()
    main(
        client=client,
        image_tag=client.images(number=1, tagged=True)[0].tag,
    )
