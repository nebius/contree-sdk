from asyncio import run
from pathlib import Path
from tempfile import NamedTemporaryFile

from contree_client.base import ContreeAsyncClient

from contree_sdk import Contree


async def main(api_client: ContreeAsyncClient):
    sdk = Contree(api_client)
    image = await sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: File as stdin input")
    with NamedTemporaryFile(mode="w", suffix=".txt") as input_file:
        input_file.write("apple\nbanana\ncherry\ndate\nfig\n")
        input_file.flush()

        result = await image.run(shell="cat | grep 'a' | sort", stdin=Path(input_file.name))
        print(f"Filter and sort result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: File as stdout output")
    with NamedTemporaryFile(mode="w", suffix=".txt") as output_file:
        result = await image.run(shell="ls -la /bin | head -5", stdout=output_file.name)
        print(f"Command exit code: {result.exit_code=}")

        with open(output_file.name) as f:
            content = f.read()
        print(f"Output written to file: {content.strip()}")

    print("\nExample 3: File pipeline - stdin to stdout")
    with (
        NamedTemporaryFile(mode="w", suffix=".txt") as input_file,
        NamedTemporaryFile(mode="w", suffix=".txt") as output_file,
    ):
        input_file.write("The quick brown fox\njumps over the lazy dog\nHello World")
        input_file.flush()

        result = await image.run(shell="grep -i 'o' | wc -l", stdin=Path(input_file.name), stdout=output_file.name)
        print(f"Pipeline exit code: {result.exit_code=}")

        with open(output_file.name) as f:
            line_count = f.read().strip()
        print(f'Lines containing "o": {line_count}')


async def run_example():
    from contree_client.asyncio import ContreeAsyncClient as DefaultContreeAsyncClient

    # The application owns one resource-bearing client and reuses it through the SDK.
    async with DefaultContreeAsyncClient.from_profile() as api_client:
        await main(api_client)


if __name__ == "__main__":
    run(run_example())
