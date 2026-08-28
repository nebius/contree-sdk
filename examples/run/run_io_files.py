from asyncio import run
from pathlib import Path
from tempfile import TemporaryDirectory

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: File as stdin input")
    with TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "input.txt"
        input_file.write_text("apple\nbanana\ncherry\ndate\nfig\n")

        result = await image.run(shell="cat | grep 'a' | sort", stdin=input_file)
        print(f"Filter and sort result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: File as stdout output")
    with TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output.txt"
        result = await image.run(shell="ls -la /bin | head -5", stdout=output_file)
        print(f"Command exit code: {result.exit_code=}")

        content = output_file.read_text()
        print(f"Output written to file: {content.strip()}")

    print("\nExample 3: File pipeline - stdin to stdout")
    with TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "input.txt"
        input_file.write_text("The quick brown fox\njumps over the lazy dog\nHello World")

        output_file = Path(tmpdir) / "output.txt"
        result = await image.run(shell="grep -i 'o' | wc -l", stdin=input_file, stdout=output_file)
        print(f"Pipeline exit code: {result.exit_code=}")

        line_count = output_file.read_text().strip()
        print(f'Lines containing "o": {line_count}')


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
