import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


@pytest.fixture
async def image(contree: Contree) -> ContreeImage:
    return await contree.images.pull("0bd59a5d-9f0d-4fab-9376-001ec247cd78")


@pytest.fixture
async def image_s(contree_s: ContreeSync) -> ContreeImageSync:
    return contree_s.images.pull("0bd59a5d-9f0d-4fab-9376-001ec247cd78")
