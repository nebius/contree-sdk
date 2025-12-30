from asyncio import run
from io import BytesIO, StringIO
from subprocess import PIPE
from tempfile import NamedTemporaryFile

from contree_sdk import Contree


async def main(client: Contree):
    image = await client.images.pull("busybox:latest")
    print(f"Pulled {image=}")

    print("\nExample 1: StringIO for stdin and stdout")
    stdin_io = StringIO("apple\nbanana\ncherry\ndate\n")
    stdout_io = StringIO()

    result = await image.run(shell="grep 'a' | sort", stdin=stdin_io, stdout=stdout_io)
    print(f"StringIO result: exit_code={result.exit_code}")
    print(f"Output in StringIO: {stdout_io.getvalue()=}")
    print(f"result.stdout is the StringIO object: {result.stdout is stdout_io}")

    print("\nExample 2: PIPE for stderr capture")
    result = await image.run(shell="echo 'to stdout'; echo 'to stderr' >&2; exit 0", stderr=PIPE)
    print(f"PIPE stderr: {result.stdout=}")
    print(f"Stderr content: {result.stderr.read().decode()=}")
    print(f"Stderr type: {type(result.stderr).__name__}")

    print("\nExample 3: Output to bytes")
    result = await image.run(shell="echo 'Hello bytes world'", stdout=bytes)
    print(f"Bytes output: {result.stdout=}")
    print(f"Output type: {type(result.stdout).__name__}")

    print("\nExample 4: open() file object for input")
    with NamedTemporaryFile(mode="w", suffix=".txt") as temp_file:
        temp_file.write("line1\nline2\nline3\n")
        temp_file.flush()

        with open(temp_file.name) as file_obj:
            result = await image.run(shell="wc -l", stdin=file_obj)
            print(f"File object input: {result.stdout=}, {result.exit_code=}")

    print("\nExample 5: BytesIO for binary data")
    binary_data = BytesIO(b"binary\ndata\nlines\n")

    result = await image.run(shell="wc -l", stdin=binary_data)
    print(f"BytesIO input: {result.stdout=}, {result.exit_code=}")


if __name__ == "__main__":
    run(
        main(
            client=Contree(),
        )
    )
