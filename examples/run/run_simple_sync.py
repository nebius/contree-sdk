from contree_sdk import ContreeSync


def main(client: ContreeSync):
    image = client.images.use("busybox:latest")
    print(f"Using {image=}")

    result = image.run(shell="echo 'Hello World'").wait()
    print(f"Simple echo: {result.stdout=}, {result.stderr=}, {result.exit_code=}")

    result = image.run(shell="pwd").wait()
    print(f"Current directory: {result.stdout=}, {result.exit_code=}")

    result = image.run(shell="ls -la").wait()
    print(f"Directory listing: {result.stdout=}, {result.exit_code=}")

    result = image.run(shell="cat -", stdin="Hello from stdin\n").wait()
    print(f"Cat with stdin: {result.stdout=}, {result.exit_code=}")

    result = image.run(shell="echo 'Error message' >&2; exit 1").wait()
    print(f"Error command: {result.stdout=}, {result.stderr=}, {result.exit_code=}")


if __name__ == "__main__":
    main(
        client=ContreeSync(),
    )
