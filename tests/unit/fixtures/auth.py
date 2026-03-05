from uuid import uuid4

import pytest
from pytest_httpx import HTTPXMock

from tests.unit.fixtures.utils import r


@pytest.fixture
def token_uuid() -> str:
    return str(uuid4())


@pytest.fixture
def api_fake_whoami(token_uuid: str, strict_httpx: HTTPXMock) -> HTTPXMock:
    strict_httpx.add_response(
        method="GET",
        url=r(".*/whoami"),
        json={
            "token_uuid": token_uuid,
            "token_expiration": None,
            "permissions": {"spawn": True, "import": False},
            "limits": {"instance_max_concurrency": 4},
            "operations_stat": {},
        },
        is_optional=True,
    )
    return strict_httpx
