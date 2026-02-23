from tempfile import NamedTemporaryFile

from contree_sdk import ContreeSync


def main(client: ContreeSync):
    image = client.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Create file and download it")
    result = image.run(
        shell="sh -c 'echo \"Generated inside container at $(date)\" > /tmp/output.txt'", disposable=False
    ).wait()

    with NamedTemporaryFile(mode="w+") as local_file:
        result.download("/tmp/output.txt", local_file.name)
        with open(local_file.name) as f:
            content = f.read()
        print(f"Downloaded file content: {content.strip()}")

    print("\nExample 2: List /etc directory contents")
    etc_files = image.ls("/etc")
    print(f"Files in /etc: {etc_files=}")

    print("\nExample 3: Download system file")
    with NamedTemporaryFile(mode="w+") as local_file:
        image.download("/etc/passwd", local_file.name)
        with open(local_file.name) as f:
            passwd_content = f.read()
        print(f"System passwd file (first 3 lines): {passwd_content.splitlines()[:3]}")


if __name__ == "__main__":
    main(
        client=ContreeSync(),
    )
