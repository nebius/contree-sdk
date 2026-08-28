import os

from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient) -> None:
    # The caller owns the passed client's transport lifecycle.
    sdk = ContreeSync(api_client)

    # Get images (to verify that connection works)
    sdk.images()


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    token = os.getenv("NEBIUS_API_KEY")
    if not token:
        os.environ["NEBIUS_API_KEY"] = input("Please enter Nebius IAM token: ")
    with DefaultContreeClient(os.environ["NEBIUS_API_KEY"]) as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
