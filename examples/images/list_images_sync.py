from datetime import datetime, timedelta

from contree_sdk import ContreeSync
from contree_sdk.utils.models.image import ImageKind


def main(client: ContreeSync):
    all_images = client.images()
    print(f"Loaded {all_images=}")

    limited_images = client.images(number=3)
    print(f"Found {len(limited_images)=}")

    tagged_images = client.images(tagged=True)
    print(f"Found {len(tagged_images)=}")

    imported_images = client.images(kind=ImageKind.IMPORTED)
    print(f"Found {len(imported_images)=}")

    recent_images = client.images(since=datetime.now() - timedelta(days=7), number=5)
    print(f"Found {len(recent_images)=}")


if __name__ == "__main__":
    main(client=ContreeSync())
