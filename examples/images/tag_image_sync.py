from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image_tag = sdk.images(number=1, tagged=True)[0].tag
    if image_tag is None:
        raise RuntimeError("The selected image must have a tag")

    image = sdk.images.use(image_tag, strict=True)
    print(f"Original: {image.uuid=}, {image.tag=}")

    tagged = image.tag_as("my-custom-tag:v1")
    print(f"After tag_as: {tagged.uuid=}, {tagged.tag=}")

    untagged = tagged.untag()
    print(f"After untag: {untagged.uuid=}, {untagged.tag=}")

    result = image.run(shell="echo hello", tag="my-result:v1", disposable=False).wait()
    print(f"Run result: {result.uuid=}, {result.tag=}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
