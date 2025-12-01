from dataclasses import replace

import pytest
from httpx import TimeoutException

from contree_sdk import Contree
from contree_sdk.config import ContreeConfig


async def test_client_timeout(contree_config: ContreeConfig):
    config = replace(contree_config, transport_timeout=0.00001)

    client = Contree(config)
    with pytest.raises(TimeoutException):
        await client.images()
