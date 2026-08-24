from asyncio import run

from contree_client.asyncio import ContreeAsyncClient
from contree_client.exceptions import NotFoundError
from contree_client.models import ImageImportRegistry
from contree_client.types import ContreeAsyncClient as ContreeAsyncClientBase


async def main(client: ContreeAsyncClientBase, image_tag: str):
    print(f"Selected {image_tag=}")

    print("\nResolving an already-imported image by tag:")
    try:
        image_uuid = await client.resolve_image(f"tag:{image_tag}")
        print(f"Resolved: {image_uuid=}")
    except NotFoundError:
        print(f"{image_tag!r} is not imported yet")

    print("\nImporting a public image from a registry:")
    operation_uuid = await client.import_image(
        ImageImportRegistry(url="docker://ghcr.io/linuxserver/code-server:latest"),
        tag="code-server:latest",
    )
    operation = await client.wait_operation(operation_uuid)
    print(f"Imported: {operation.result_image_uuid=}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile(), image_tag="busybox:latest"))
