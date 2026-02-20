from asyncio import run

from contree_sdk import Contree


async def main(client: Contree):
    image = await client.images.pull("alpine:3.20")
    print(f"Pulled {image=}")

    print("\nExample 1: Simple command execution")
    result = await image.run("/bin/echo", args=["Hello from command parameter!"])
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: Command with arguments")
    result = await image.run("/bin/ls", args=["-la", "/tmp"])
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 3: Command with environment variables")
    result = await image.run("/bin/printenv", args=["MY_VAR"], env={"MY_VAR": "test_value"})
    print(f"Result: {result.stdout=}, {result.exit_code=}")


if __name__ == "__main__":
    run(
        main(
            client=Contree(),
        )
    )
