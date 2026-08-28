from pathlib import Path
from tempfile import TemporaryDirectory

from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image = sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Create file and download it")
    result = image.run(
        shell="sh -c 'echo \"Generated inside container at $(date)\" > /tmp/output.txt'", disposable=False
    ).wait()

    with TemporaryDirectory() as tmpdir:
        local_file = Path(tmpdir) / "output.txt"
        result.download("/tmp/output.txt", local_file)
        content = local_file.read_text()
        print(f"Downloaded file content: {content.strip()}")

    print("\nExample 2: List /etc directory contents")
    etc_files = image.ls("/etc")
    print(f"Files in /etc: {etc_files=}")

    print("\nExample 3: Download system file")
    with TemporaryDirectory() as tmpdir:
        local_file = Path(tmpdir) / "passwd"
        image.download("/etc/passwd", local_file)
        passwd_content = local_file.read_text()
        print(f"System passwd file (first 3 lines): {passwd_content.splitlines()[:3]}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
