from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from contree_client.models import FileResponse


@pytest.fixture
def file_uuid() -> str:
    return str(uuid4())


@pytest.fixture
def file_sha256() -> str:
    return "1c338c24f4a82e6dc440204d8d6a08058a58136d3e01b4f7aa0f7588b51ba197"


def queue_upload(api: Any, file_uuid: str, file_sha256: str, *, size: int = 4) -> None:
    api.mock("ensure_file", FileResponse(uuid=file_uuid, sha256=file_sha256, size=size))
