from contree_client.models import ImageListResponse
from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient


def image_count(response: ImageListResponse) -> int:
    return len(response.images) if isinstance(response.images, list) else 0


def main(client: ContreeSyncClient):
    images = client.list_images(limit=1)
    print(f"Connected, {image_count(images)} image(s) visible")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
