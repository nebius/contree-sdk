from asyncio import run

from contree_sdk import Contree


async def main(client: Contree):
    image = await client.images.pull("busybox:latest")
    print(f"Pulled {image=}")

    result = await image.run(shell="echo 'Hello World'")
    print(f"Simple echo: {result.stdout=}, {result.stderr=}, {result.exit_code=}")

    result = await image.run(shell="pwd")
    print(f"Current directory: {result.stdout=}, {result.exit_code=}")

    result = await image.run(shell="ls -la")
    print(f"Directory listing: {result.stdout=}, {result.exit_code=}")

    result = await image.run(shell="cat -", stdin="Hello from stdin\n")
    print(f"Cat with stdin: {result.stdout=}, {result.exit_code=}")

    result = await image.run(shell="echo 'Error message' >&2; exit 1")
    print(f"Error command: {result.stdout=}, {result.stderr=}, {result.exit_code=}")


if __name__ == "__main__":
    run(main(client=Contree()))
