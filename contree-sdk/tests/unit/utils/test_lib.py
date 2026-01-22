from dataclasses import replace

import pytest
from httpx import ReadTimeout, Response

from contree_sdk import Contree
from contree_sdk._internals.utils.exception import wrap_api_exception
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import ApiTimeoutError


async def test_read_timeout(fake_contree_config: ContreeConfig, httpbin):
    config = replace(fake_contree_config, transport_timeout=1)
    contree = Contree(config=config)
    client = contree._api

    read_timeout = contree.config.transport_timeout
    numbytes = 2
    duration = int(read_timeout * (numbytes + 2))

    req = client._client.build_request(
        "GET",
        f"{httpbin.url}/drip?{numbytes=}&{duration=}&delay=0&code=200",
    )

    with pytest.raises(ReadTimeout) as e_info:
        await client._send_request(req)

    exc = e_info.value
    assert exc is not None
    assert isinstance(exc, ReadTimeout)
    resp = getattr(exc, "response", None)
    assert isinstance(resp, Response)
    assert isinstance(resp.headers["content-type"], str)

    new_exp = wrap_api_exception(exc)
    assert isinstance(new_exp, ApiTimeoutError)
    assert new_exp.timeout_type == "read"
    assert isinstance(new_exp.response.headers["content-type"], str)
