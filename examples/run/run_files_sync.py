from tempfile import NamedTemporaryFile

from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync
from contree_sdk.utils.models.file import UploadFileSpec


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image = sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Local file upload to image")
    with NamedTemporaryFile(mode="w", suffix=".txt") as test_file:
        test_file.write("some txt file\nsecond line\n\nlast line\n")
        test_file.flush()

        result = image.run(shell=f"cat /{test_file.name.split('/')[-1]} | grep line", files=[test_file.name]).wait()
        print(f"Run with local file: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: Upload file via contree.files and use in image")
    with NamedTemporaryFile(mode="w", suffix=".sh") as script_file:
        script_file.write("#!/bin/sh\necho 'Hello from uploaded script'\necho 'Working directory:'\npwd\n")
        script_file.flush()

        uploaded_file = sdk.files.upload(script_file.name)
        print(f"Uploaded file: {uploaded_file=}")

        result = image.run(
            shell="sh /file.sh",
            files={"file.sh": UploadFileSpec(source=uploaded_file)},
        ).wait()
        print(f"Run with uploaded file: {result.stdout=}, {result.stderr=}, {result.exit_code=}")

    print("\nExample 3: Bake files into a new image with apply_files")
    with NamedTemporaryFile(mode="w", suffix=".txt") as f:
        f.write("hello from baked file\n")
        f.flush()
        baked = image.apply_files({"baked.txt": f.name})
        result = baked.run(shell="cat /baked.txt").wait()
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

        result = image.run(
            shell="chmod +x /script.sh && sh /script.sh",
            files={"data.txt": data_file.name, "script.sh": script_file.name},
        ).wait()
        print(f"Multiple files result: {result.stdout=}, {result.stderr=}, {result.exit_code=}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
