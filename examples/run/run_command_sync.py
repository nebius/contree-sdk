from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    image = sdk.images.use("alpine:3.20", strict=True)
    print(f"Pulled {image=}")

    print("\nExample 1: Simple command execution")
    result = image.run("/bin/echo", args=["Hello from command parameter!"]).wait()
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 2: Command with arguments")
    result = image.run("/bin/ls", args=["-la", "/tmp"]).wait()
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 3: Command with environment variables")
    result = image.run("/bin/printenv", args=["MY_VAR"], env={"MY_VAR": "test_value"}).wait()
    print(f"Result: {result.stdout=}, {result.exit_code=}")

    print("\nExample 4: Preserve environment variables in the resulting image")
    prepared = image.run(
        shell="true",
        env={"MY_PERSISTED_VAR": "persisted_value"},
        preserve_env=True,
        disposable=False,
    ).wait()
    result = prepared.run("/bin/printenv", args=["MY_PERSISTED_VAR"]).wait()
    print(f"Result: {result.stdout=}, {result.exit_code=}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
