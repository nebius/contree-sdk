from asyncio import run
from uuid import UUID

from contree_sdk import Contree, ContreeSync


async def main(client: Contree, image_uuid: UUID, image_tag: str):
    print(f"Selected {image_uuid=}")
    print(f"Selected {image_tag=}")

    print("\nPulling by UUID (strict):")
    result = await client.images.use(image_uuid, strict=True)
    print(f"Pulled by UUID: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nPulling by tag (strict):")
    result = await client.images.use(image_tag, strict=True)
    print(f"Pulled by tag: {result.uuid=}, {result.tag=}, {result.state=}")

    print("\nImporting public image using oci:")
    result = await client.images.oci("docker://ghcr.io/linuxserver/code-server:latest")
    print(f"Pulled public: {result.uuid=}, {result.tag=}, {result.state=}")


if __name__ == "__main__":
    client_sync = ContreeSync()
    run(
        main(
            client=Contree(),
            image_uuid=client_sync.images(number=1)[0].uuid,
            image_tag=client_sync.images(number=1, tagged=True)[0].tag,
        )
    )
