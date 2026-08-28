from asyncio import run
from io import BytesIO, StringIO
from pathlib import Path
from subprocess import PIPE
from tempfile import TemporaryDirectory
from typing import Literal, cast

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: StringIO for stdin and stdout")
    stdin_io = StringIO("apple\nbanana\ncherry\ndate\n")
    stdout_io = StringIO()

    result = await image.run(shell="grep 'a' | sort", stdin=stdin_io, stdout=stdout_io)
    print(f"StringIO result: exit_code={result.exit_code}")
    print(f"Output in StringIO: {stdout_io.getvalue()=}")
    print(f"result.stdout is the StringIO object: {result.stdout is stdout_io}")

    print("\nExample 2: PIPE for stderr capture")
    result = await image.run(
        shell="echo 'to stdout'; echo 'to stderr' >&2; exit 0",
        stderr=cast("Literal[-1]", PIPE),
    )
    print(f"PIPE stderr: {result.stdout=}")
    print(f"Stderr content: {result.stderr.read().decode()=}")
    print(f"Stderr type: {type(result.stderr).__name__}")

    print("\nExample 3: Output to bytes")
    result = await image.run(shell="echo 'Hello bytes world'", stdout=bytes)
    print(f"Bytes output: {result.stdout=}")
    print(f"Output type: {type(result.stdout).__name__}")

    print("\nExample 4: open() file object for input")
    with TemporaryDirectory() as tmpdir:
        temp_file = Path(tmpdir) / "temp.txt"
        temp_file.write_text("line1\nline2\nline3\n")

        with open(temp_file) as file_obj:
            result = await image.run(shell="wc -l", stdin=file_obj)
            print(f"File object input: {result.stdout=}, {result.exit_code=}")

    print("\nExample 5: BytesIO for binary data")
    binary_data = BytesIO(b"binary\ndata\nlines\n")

    result = await image.run(shell="wc -l", stdin=binary_data)
    print(f"BytesIO input: {result.stdout=}, {result.exit_code=}")


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
