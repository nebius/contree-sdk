from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    contree = ContreeSync(api_client)
    image = contree.images.use("busybox:latest")

    prepared = image.run(
        shell="true",
        env={"MY_PERSISTED_VAR": "persisted_value"},
        preserve_env=True,
        disposable=False,
    ).wait()
    result = prepared.run("/bin/printenv", args=["MY_PERSISTED_VAR"]).wait()
    print(result.stdout)


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
