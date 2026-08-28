from dataclasses import replace

import pytest
from httpx import ReadTimeout
from pytest_httpx import HTTPXMock

from contree_sdk import Contree
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import ApiTimeoutError


async def test_read_timeout(fake_contree_config: ContreeConfig, httpx_mock: HTTPXMock):
    config = replace(fake_contree_config, transport_timeout=1)
    contree = Contree(config=config)
    httpx_mock.add_exception(ReadTimeout("stream stalled"))

    with pytest.raises(ApiTimeoutError) as e_info:
        await contree.images()

    assert e_info.value.timeout_type == "read"
