from uuid import UUID

from contree_sdk import ContreeSync


def main(client: ContreeSync, image_uuid: UUID, image_tag: str):
    print(f"Selected {image_uuid=}")
    print(f"Selected {image_tag=}")

    print("\nPulling by UUID:")
    result = client.images.pull(image_uuid)
    print(f"Pull by UUID: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nPulling by tag:")
    result = client.images.pull(image_tag)
    print(f"Pull by tag: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nImporting public image:")
    result = client.images.pull("docker://ghcr.io/linuxserver/code-server:latest")
    print(f"Import public: {result.uuid=}, {result.tag=}, {result.state=}")


if __name__ == "__main__":
    client = ContreeSync()
    main(
        client=client,
        image_uuid=client.images(number=1)[0].uuid,
        image_tag=client.images(number=1, tagged=True)[0].tag,
    )
