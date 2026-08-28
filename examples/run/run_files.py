from asyncio import run
from pathlib import Path
from tempfile import TemporaryDirectory

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree
from contree_sdk.utils.models.file import UploadFileSpec


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Local file upload to image")
    with TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("some txt file\nsecond line\n\nlast line\n")

        result = await image.run(shell=f"cat /{test_file.name} | grep line", files=[test_file])
        print(f"Run with local file: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: Upload file via contree.files and use in image")
    with TemporaryDirectory() as tmpdir:
        script_file = Path(tmpdir) / "script.sh"
        script_file.write_text("#!/bin/sh\necho 'Hello from uploaded script'\necho 'Working directory:'\npwd\n")

        uploaded_file = await sdk.files.upload(script_file)
        print(f"Uploaded file: {uploaded_file=}")

        result = await image.run(shell="sh /file.sh", files={"file.sh": UploadFileSpec(source=uploaded_file)})
        print(f"Run with uploaded file: {result.stdout=}, {result.stderr=}, {result.exit_code=}")

    print("\nExample 3: Bake files into a new image with apply_files")
    with TemporaryDirectory() as tmpdir:
        baked_file = Path(tmpdir) / "baked.txt"
        baked_file.write_text("hello from baked file\n")
        baked = await image.apply_files({"baked.txt": baked_file})
        result = await baked.run(shell="cat /baked.txt")
        print(f"File is present in new image: {result.stdout=}")

    print("\nExample 4: Multiple files working together")
    with TemporaryDirectory() as tmpdir:
        data_file = Path(tmpdir) / "data.txt"
        data_file.write_text("apple\nbanana\ncherry\ndate\n")

        script_file = Path(tmpdir) / "script.sh"
        script_file.write_text(
            "#!/bin/bash\necho 'Processing data:'\ncat /data.txt | grep -E '^[ab]'"
            "\necho 'Found items starting with a or b'"
        )

        result = await image.run(
            shell="chmod +x /script.sh && sh /script.sh",
            files={"data.txt": data_file, "script.sh": script_file},
        )
        print(f"Multiple files result: {result.stdout=}, {result.stderr=}, {result.exit_code=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
