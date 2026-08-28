from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from tests.unit.fixtures.operations import queue_run


FILE_UUID = "6a1b0d3c-7e8f-4a9b-9c1d-2e3f4a5b6c7d"
FILE_SHA256 = "1c338c24f4a82e6dc440204d8d6a08058a58136d3e01b4f7aa0f7588b51ba197"


RUN_STDIN = "my input\n"
RUN_STDOUT = RUN_STDIN + "this is stdout\n"
RUN_STDERR = "this is stderr\n"


# `api_fake_popen_shell`/`api_fake_popen_communicate` back README `fixture:`
# markers via `tests/unit/docs/conftest.py`'s direct import -- that injection
# mechanism needs named fixtures, so these two stay (unlike the other
# `api_fake_*` fixtures that used to live in this module, now inlined into
# their consuming tests).
@pytest.fixture
def api_fake_popen_shell(fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api_s, stdout="Hello World\n", stderr="Error message\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_popen_communicate(fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api_s, stdout="test line\ntest again\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s
