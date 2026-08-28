from contree_client.models import ImageListResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient
from examples.client.client import main as client_main
from examples.client.client_sync import main as client_main_s


async def test_client_example(fake_api: ContreeAsyncClient):
    fake_api.mock("list_images", ImageListResponse(images=[]))
    await client_main(fake_api)


def test_client_example_s(fake_api_s: ContreeClient):
    fake_api_s.mock("list_images", ImageListResponse(images=[]))
    client_main_s(fake_api_s)
