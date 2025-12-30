from asyncio import run
from datetime import datetime, timedelta

from contree_sdk import Contree
from contree_sdk.utils.models.image import ImageKind


async def main(client: Contree):
    all_images = await client.images()
    print(f"Loaded {all_images=}")

    limited_images = await client.images(number=3)
    print(f"Found {len(limited_images)=}")

    tagged_images = await client.images(tagged=True)
    print(f"Found {len(tagged_images)=}")

    imported_images = await client.images(kind=ImageKind.IMPORTED)
    print(f"Found {len(imported_images)=}")

    recent_images = await client.images(since=datetime.now() - timedelta(days=7), number=5)
    print(f"Found {len(recent_images)=}")


if __name__ == "__main__":
    run(main(client=Contree()))
