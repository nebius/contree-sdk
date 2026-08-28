from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image_uuid = sdk.images(number=1)[0].uuid
    image_tag = sdk.images(number=1, tagged=True)[0].tag
    if image_uuid is None or image_tag is None:
        raise RuntimeError("The selected images must have a UUID and tag")

    print(f"Selected {image_uuid=}")
    print(f"Selected {image_tag=}")

    print("\nPulling by UUID (strict):")
    result = sdk.images.use(image_uuid, strict=True)
    print(f"Pull by UUID: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nPulling by tag (strict):")
    result = sdk.images.use(image_tag, strict=True)
    print(f"Pull by tag: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nImporting public image using oci:")
    result = sdk.images.oci("docker://ghcr.io/linuxserver/code-server:latest")
    print(f"Import public: {result.uuid=}, {result.tag=}, {result.state=}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
