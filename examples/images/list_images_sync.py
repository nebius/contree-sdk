from datetime import datetime, timedelta

from contree_client.models import ImageListResponse
from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient


def image_count(response: ImageListResponse) -> int:
    return len(response.images) if isinstance(response.images, list) else 0


def main(client: ContreeSyncClient):
    all_images = client.list_images()
    print(f"Loaded {image_count(all_images)} image(s)")

    limited = client.list_images(limit=3)
    print(f"Limited to {image_count(limited)} image(s)")

    tagged_only = client.list_images(tagged=True)
    print(f"Tagged images: {image_count(tagged_only)}")

    since = datetime.now().astimezone() - timedelta(days=7)
    recent = client.list_images(since=since.isoformat(), limit=5)
    print(f"Created in the last week: {image_count(recent)}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
