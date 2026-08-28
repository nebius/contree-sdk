from io import BytesIO, StringIO
from pathlib import Path
from subprocess import PIPE
from tempfile import TemporaryDirectory
from typing import BinaryIO, Literal, cast

from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image = sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: StringIO for stdin and stdout")
    stdin_io = StringIO("apple\nbanana\ncherry\ndate\n")
    stdout_io = StringIO()

    result = image.run(shell="grep 'a' | sort", stdin=stdin_io, stdout=stdout_io).wait()
    print(f"StringIO result: exit_code={result.exit_code}")
    print(f"Output in StringIO: {stdout_io.getvalue()=}")
    print(f"result.stdout is the StringIO object: {result.stdout is stdout_io}")

    print("\nExample 2: PIPE for stderr capture")
    result = image.run(
        shell="echo 'to stdout'; echo 'to stderr' >&2; exit 0",
        stderr=cast("Literal[-1]", PIPE),
    ).wait()
    stderr = cast("BinaryIO", result.stderr)
    print(f"PIPE stderr: {result.stdout=}")
    print(f"Stderr content: {stderr.read().decode()=}")
    print(f"Stderr type: {type(result.stderr).__name__}")

    print("\nExample 3: Output to bytes")
    result = image.run(shell="echo 'Hello bytes world'", stdout=bytes).wait()
    print(f"Bytes output: {result.stdout=}")
    print(f"Output type: {type(result.stdout).__name__}")

    print("\nExample 4: open() file object for input")
    with TemporaryDirectory() as tmpdir:
        temp_file = Path(tmpdir) / "temp.txt"
        temp_file.write_text("line1\nline2\nline3\n")

        with open(temp_file) as file_obj:
            result = image.run(shell="wc -l", stdin=file_obj).wait()
            print(f"File object input: {result.stdout=}, {result.exit_code=}")

    print("\nExample 5: BytesIO for binary data")
    binary_data = BytesIO(b"binary\ndata\nlines\n")

    result = image.run(shell="wc -l", stdin=binary_data).wait()
    print(f"BytesIO input: {result.stdout=}, {result.exit_code=}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
