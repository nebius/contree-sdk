from pathlib import Path
from tempfile import TemporaryDirectory

from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image = sdk.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: File as stdin input")
    with TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "input.txt"
        input_file.write_text("apple\nbanana\ncherry\ndate\nfig\n")

        result = image.run(shell="cat | grep 'a' | sort", stdin=input_file).wait()
        print(f"Filter and sort result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: File as stdout output")
    with TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output.txt"
        result = image.run(shell="ls -la /bin | head -5", stdout=output_file).wait()
        print(f"Command exit code: {result.exit_code=}")

        content = output_file.read_text()
        print(f"Output written to file: {content.strip()}")

    print("\nExample 3: File pipeline - stdin to stdout")
    with TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "input.txt"
        input_file.write_text("The quick brown fox\njumps over the lazy dog\nHello World")

        output_file = Path(tmpdir) / "output.txt"
        result = image.run(shell="grep -i 'o' | wc -l", stdin=input_file, stdout=output_file).wait()
        print(f"Pipeline exit code: {result.exit_code=}")

        line_count = output_file.read_text().strip()
        print(f'Lines containing "o": {line_count}')


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
