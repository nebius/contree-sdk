import os
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


async def run_with_client() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        await main(client=client)


if __name__ == "__main__":
    run(run_with_client())


def test_list_images(doc_api, capsys):
    import runpy

    client = doc_api.async_client
    # An empty response is valid and still exercises every filter.
    client.mock("list_images", ImageListResponse(images=[]))
    runpy.run_path(__file__, run_name="__main__")

    calls = client.calls_for("list_images")
    assert len(calls) == 4
    assert calls[0].kwargs == {}
    assert calls[1].kwargs == {"limit": 3}
    assert calls[2].kwargs == {"tagged": True}
    assert calls[3].kwargs["limit"] == 5
    since = datetime.fromisoformat(calls[3].kwargs["since"])
    assert abs((datetime.now().astimezone() - since).total_seconds() - 7 * 86400) < 10
    assert capsys.readouterr().out == (
        "Loaded 0 image(s)\nLimited to 0 image(s)\nTagged images: 0\nCreated in the last week: 0\n"
    )
