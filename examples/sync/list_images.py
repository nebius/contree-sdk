import os
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
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        main(client=client)


def test_list_images(doc_api, capsys):
    import runpy

    client = doc_api.sync
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
