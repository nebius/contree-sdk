from asyncio import run

from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import ImageListResponse
from contree_client.types import ContreeAsyncClient as ContreeAsyncClientBase


def image_count(response: ImageListResponse) -> int:
    return len(response.images) if isinstance(response.images, list) else 0


async def main(client: ContreeAsyncClientBase):
    images = await client.list_images(limit=1)
    print(f"Connected, {image_count(images)} image(s) visible")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
