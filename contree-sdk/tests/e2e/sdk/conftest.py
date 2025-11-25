import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.session._async import ContreeSession
from contree_sdk.sdk.objects.session._sync import ContreeSessionSync


@pytest.fixture
async def image(contree: Contree) -> ContreeImage:
    images = await contree.images()
    return images[0]


@pytest.fixture
def image_s(contree_s: ContreeSync) -> ContreeImageSync:
    images = contree_s.images()
    return images[0]


@pytest.fixture
async def session(image: ContreeImage) -> ContreeSession:
    return image.session()


@pytest.fixture
async def session_s(image_s: ContreeImageSync) -> ContreeSessionSync:
    return image_s.session()
