from asyncio import run
from tempfile import NamedTemporaryFile

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree
from contree_sdk.utils.models.file import UploadFileSpec


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Local file upload to image")
    with NamedTemporaryFile(mode="w", suffix=".txt") as test_file:
        test_file.write("some txt file\nsecond line\n\nlast line\n")
        test_file.flush()

        result = await image.run(shell=f"cat /{test_file.name.split('/')[-1]} | grep line", files=[test_file.name])
        print(f"Run with local file: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: Upload file via contree.files and use in image")
    with NamedTemporaryFile(mode="w", suffix=".sh") as script_file:
        script_file.write("#!/bin/sh\necho 'Hello from uploaded script'\necho 'Working directory:'\npwd\n")
        script_file.flush()

        uploaded_file = await sdk.files.upload(script_file.name)
        print(f"Uploaded file: {uploaded_file=}")

        result = await image.run(shell="sh /file.sh", files={"file.sh": UploadFileSpec(source=uploaded_file)})
        print(f"Run with uploaded file: {result.stdout=}, {result.stderr=}, {result.exit_code=}")

    print("\nExample 3: Bake files into a new image with apply_files")
    with NamedTemporaryFile(mode="w", suffix=".txt") as f:
        f.write("hello from baked file\n")
        f.flush()
        baked = await image.apply_files({"baked.txt": f.name})
        result = await baked.run(shell="cat /baked.txt")
        print(f"File is present in new image: {result.stdout=}")

    print("\nExample 4: Multiple files working together")
    with (
        NamedTemporaryFile(mode="w", suffix=".txt") as data_file,
        NamedTemporaryFile(mode="w", suffix=".sh") as script_file,
    ):
        data_file.write("apple\nbanana\ncherry\ndate\n")
        data_file.flush()

        script_file.write(
            "#!/bin/bash\necho 'Processing data:'\ncat /data.txt | grep -E '^[ab]'"
            "\necho 'Found items starting with a or b'"
        )
        script_file.flush()

        result = await image.run(
            shell="chmod +x /script.sh && sh /script.sh",
            files={"data.txt": data_file.name, "script.sh": script_file.name},
        )
        print(f"Multiple files result: {result.stdout=}, {result.stderr=}, {result.exit_code=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
