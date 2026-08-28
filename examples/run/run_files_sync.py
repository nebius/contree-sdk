from pathlib import Path
from tempfile import TemporaryDirectory

from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync
from contree_sdk.utils.models.file import UploadFileSpec


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image = sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Local file upload to image")
    with TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("some txt file\nsecond line\n\nlast line\n")

        result = image.run(shell=f"cat /{test_file.name} | grep line", files=[test_file]).wait()
        print(f"Run with local file: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: Upload file via contree.files and use in image")
    with TemporaryDirectory() as tmpdir:
        script_file = Path(tmpdir) / "script.sh"
        script_file.write_text("#!/bin/sh\necho 'Hello from uploaded script'\necho 'Working directory:'\npwd\n")

        uploaded_file = sdk.files.upload(script_file)
        print(f"Uploaded file: {uploaded_file=}")

        result = image.run(
            shell="sh /file.sh",
            files={"file.sh": UploadFileSpec(source=uploaded_file)},
        ).wait()
        print(f"Run with uploaded file: {result.stdout=}, {result.stderr=}, {result.exit_code=}")

    print("\nExample 3: Bake files into a new image with apply_files")
    with TemporaryDirectory() as tmpdir:
        baked_file = Path(tmpdir) / "baked.txt"
        baked_file.write_text("hello from baked file\n")
        baked = image.apply_files({"baked.txt": baked_file})
        result = baked.run(shell="cat /baked.txt").wait()
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

        result = image.run(
            shell="chmod +x /script.sh && sh /script.sh",
            files={"data.txt": data_file, "script.sh": script_file},
        ).wait()
        print(f"Multiple files result: {result.stdout=}, {result.stderr=}, {result.exit_code=}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
