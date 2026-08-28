from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    base = sdk.images.use("alpine:latest")

    child = base.run(shell='echo "$RANDOM" > /tmp/random.txt', disposable=False).wait()
    print(f"Child created from base, UUID: {child.uuid}\n")

    for i, letter in enumerate(["A", "B", "C"], 1):
        gc = child.run(
            shell=f"echo '{letter}' >> /tmp/random.txt && cat /tmp/random.txt",
            disposable=False,
        ).wait()
        if not isinstance(gc.stdout, str):
            raise TypeError("Expected text output")
        print(f"Grandchild {i}: {gc.stdout.strip()}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
