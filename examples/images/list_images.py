from asyncio import run
from datetime import datetime, timedelta

from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import ImageListResponse
from contree_client.types import ContreeAsyncClient as ContreeAsyncClientBase


def image_count(response: ImageListResponse) -> int:
    return len(response.images) if isinstance(response.images, list) else 0


async def main(client: ContreeAsyncClientBase):
    all_images = await client.list_images()
    print(f"Loaded {image_count(all_images)} image(s)")

    limited = await client.list_images(limit=3)
    print(f"Limited to {image_count(limited)} image(s)")

    tagged_only = await client.list_images(tagged=True)
    print(f"Tagged images: {image_count(tagged_only)}")

    since = datetime.now().astimezone() - timedelta(days=7)
    recent = await client.list_images(since=since.isoformat(), limit=5)
    print(f"Created in the last week: {image_count(recent)}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
