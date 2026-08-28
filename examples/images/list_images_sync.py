from datetime import datetime, timedelta

from contree_client.base import ContreeSyncClient

from contree_sdk import ContreeSync


def main(api_client: ContreeSyncClient):
    sdk = ContreeSync(api_client)
    all_images = sdk.images()
    print(f"Loaded {all_images=}")

    limited_images = sdk.images(number=3)
    print(f"Found {len(limited_images)=}")

    tagged_images = sdk.images(tagged=True)
    print(f"Found {len(tagged_images)=}")

    recent_images = sdk.images(since=datetime.now() - timedelta(days=7), number=5)
    print(f"Found {len(recent_images)=}")


def run_example() -> None:
    from contree_client.sync import ContreeClient as DefaultContreeClient

    with DefaultContreeClient.from_profile() as api_client:
        main(api_client)


if __name__ == "__main__":
    run_example()
