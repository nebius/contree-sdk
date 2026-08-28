from asyncio import run
from tempfile import NamedTemporaryFile

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Create file and download it")
    result = await image.run(
        shell="sh -c 'echo \"Generated inside container at $(date)\" > /tmp/output.txt'", disposable=False
    )

    with NamedTemporaryFile(mode="w+") as local_file:
        await result.download("/tmp/output.txt", local_file.name)
        with open(local_file.name) as f:
            content = f.read()
        print(f"Downloaded file content: {content.strip()}")

    print("\nExample 2: List /etc directory contents")
    etc_files = await image.ls("/etc")
    print(f"Files in /etc: {etc_files=}")

    print("\nExample 3: Download system file")
    with NamedTemporaryFile(mode="w+") as local_file:
        await image.download("/etc/passwd", local_file.name)
        with open(local_file.name) as f:
            passwd_content = f.read()
        print(f"System passwd file (first 3 lines): {passwd_content.splitlines()[:3]}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
