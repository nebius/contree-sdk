import os

from contree_client.httpx import ContreeClient

from contree_sdk import ContreeSync


def main():
    # Build the transport: contree_sdk performs no I/O of its own, the
    # caller owns auth/retries/base_url via the injected contree_client backend.
    api = ContreeClient(os.environ["NEBIUS_API_KEY"])
    client = ContreeSync(api)

    # Get images (to verify that connection works)
    client.images()


if __name__ == "__main__":
    token = os.getenv("NEBIUS_API_KEY")
    if not token:
        os.environ["NEBIUS_API_KEY"] = input("Please enter Nebius IAM token: ")
    main()
