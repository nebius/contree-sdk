from uuid import UUID

from contree_sdk import ContreeSync


def main(client: ContreeSync, image_uuid: UUID, image_tag: str):
    print(f"Selected {image_uuid=}")
    print(f"Selected {image_tag=}")

    print("\nPulling by UUID (strict):")
    result = client.images.use(image_uuid, strict=True)
    print(f"Pull by UUID: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nPulling by tag (strict):")
    result = client.images.use(image_tag, strict=True)
    print(f"Pull by tag: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nImporting public image using oci:")
    result = client.images.oci("docker://ghcr.io/linuxserver/code-server:latest")
    print(f"Import public: {result.uuid=}, {result.tag=}, {result.state=}")


if __name__ == "__main__":
    client = ContreeSync()
    main(
        client=client,
        image_uuid=client.images(number=1)[0].uuid,
        image_tag=client.images(number=1, tagged=True)[0].tag,
    )
