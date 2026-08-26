from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from tests.unit.fixtures.files import queue_upload
from tests.unit.fixtures.operations import queue_run


FILE_UUID = "6a1b0d3c-7e8f-4a9b-9c1d-2e3f4a5b6c7d"
FILE_SHA256 = "1c338c24f4a82e6dc440204d8d6a08058a58136d3e01b4f7aa0f7588b51ba197"


RUN_STDIN = "my input\n"
RUN_STDOUT = RUN_STDIN + "this is stdout\n"
RUN_STDERR = "this is stderr\n"


@pytest.fixture
def api_fake_run(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    queue_run(fake_api_s, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_run_deferred(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    # `not_found_first` (a transient 404 before the events stream comes up) is now
    # contree_client's own reconnect concern (`follow_operation_events`), nothing
    # left for contree_sdk to special-case -- this is the same canned run as
    # `api_fake_run`.
    queue_run(fake_api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    queue_run(fake_api_s, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_run_with_files(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    for api in (fake_api, fake_api_s):
        queue_upload(api, FILE_UUID, FILE_SHA256)
        queue_run(api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_apply_files(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    for api in (fake_api, fake_api_s):
        queue_upload(api, FILE_UUID, FILE_SHA256)
        queue_run(api, stdout="", result_image_uuid=str(result_image_uuid))
        queue_run(api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_run_preserve_env(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    # the second `.run()` chains off the first run's *result* image, so that
    # result needs a live `uuid` too (see api_fake_session_multiple_runs).
    for api in (fake_api, fake_api_s):
        queue_run(api, stdout="", result_image_uuid=str(result_image_uuid))
        queue_run(api, stdout="ok\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_run_without_preserve_env(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    for api in (fake_api, fake_api_s):
        queue_run(api, stdout="", result_image_uuid=str(result_image_uuid))
        queue_run(api, stdout="", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_run_truncated(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api, stdout="a" * 50, result_image_uuid=str(result_image_uuid))
    queue_run(fake_api_s, stdout="a" * 50, result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_session_multiple_runs(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    # a session mutates itself in place (`copy_self` is a no-op), so each
    # queued run must keep handing back a live `uuid` -- otherwise the next
    # `.run()` in the chain sees an unreferenceable (disposed) image and
    # raises `DisposableImageRunError`.
    for api in (fake_api, fake_api_s):
        for stdout in ("", "some other step\n", "some data"):
            queue_run(api, stdout=stdout, result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_slow_run(fake_api: Any, fake_api_s: Any, operation_id: str) -> Any:
    for api in (fake_api, fake_api_s):
        queue_run(api, operation_id=operation_id, stdout="")
    return fake_api_s


@pytest.fixture
def api_fake_popen(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    ls_output = (
        "total 0\n"
        "drwxr-xr-x  5 root  root  180 Jan  7 10:00 .\n"
        "drwxr-xr-x 18 root  root  360 Jan  7 10:00 ..\n"
        "crw-rw-rw-  1 root  tty   5, 0 Jan  7 10:00 tty\n"
        "crw-rw-rw-  1 root  root  1, 8 Jan  7 10:00 random\n"
        "crw-rw-rw-  1 root  root  1, 3 Jan  7 10:00 null\n"
    )
    queue_run(fake_api_s, stdout=ls_output, result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_popen_error(fake_api_s: Any, result_image_uuid: UUID) -> Any:
    error_stderr = "ls: cannot access '/totally/fake/directory': No such file or directory\n"
    queue_run(fake_api_s, stderr=error_stderr, exit_code=2, result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_popen_shell(fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api_s, stdout="Hello World\n", stderr="Error message\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_popen_stdin(fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api_s, stdout="Hello from stdin\nSecond line\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_popen_communicate(fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api_s, stdout="test line\ntest again\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_popen_env(fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_run(fake_api_s, stdout="test_value\nanother_value\n", result_image_uuid=str(result_image_uuid))
    return fake_api_s


@pytest.fixture
def api_fake_thread_pool(fake_api: Any, fake_api_s: Any) -> Any:
    for api in (fake_api, fake_api_s):
        for i in range(10):
            queue_run(api, stdout=f"{10000 + i * 1000}\n")
    return fake_api_s
