from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    contree = ContreeSync(api_client)
    image = contree.images.use("ubuntu:latest")
    result = image.run(shell="echo hello").wait()
    print(result.stdout)


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
