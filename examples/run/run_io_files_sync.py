from pathlib import Path
from tempfile import NamedTemporaryFile

from contree_sdk import ContreeSync


def main(client: ContreeSync):
    image = client.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: File as stdin input")
    with NamedTemporaryFile(mode="w", suffix=".txt") as input_file:
        input_file.write("apple\nbanana\ncherry\ndate\nfig\n")
        input_file.flush()

        result = image.run(shell="cat | grep 'a' | sort", stdin=Path(input_file.name)).wait()
        print(f"Filter and sort result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: File as stdout output")
    with NamedTemporaryFile(mode="w", suffix=".txt") as output_file:
        result = image.run(shell="ls -la /bin | head -5", stdout=output_file.name).wait()
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

        result = image.run(shell="grep -i 'o' | wc -l", stdin=Path(input_file.name), stdout=output_file.name).wait()
        print(f"Pipeline exit code: {result.exit_code=}")

        with open(output_file.name) as f:
            line_count = f.read().strip()
        print(f'Lines containing "o": {line_count}')


if __name__ == "__main__":
    main(
        client=ContreeSync(),
    )
