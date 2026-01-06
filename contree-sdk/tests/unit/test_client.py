import pytest

from contree_sdk import Contree
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import ForbiddenError


async def test_fake_token(fake_contree_config: ContreeConfig):
    client = Contree(token="fake-token")
    with pytest.raises(ForbiddenError):
        await client.images()
