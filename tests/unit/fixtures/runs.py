from uuid import UUID, uuid4

import pytest
from contree_client.models import EventResources
from pytest_httpx import HTTPXMock

from tests.unit.fixtures.files import add_file_responses
from tests.unit.fixtures.operations import ProcessState, SlowEventStream, add_base_responses, add_operation_responses
from tests.unit.fixtures.utils import r


def create_process_state(exit_code: int = 0) -> ProcessState:
    return ProcessState(
        continued=False,
        core_dump=False,
        exit_code=exit_code,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )


def add_inspect_by_uuid_response(httpx_mock: HTTPXMock, image_uuid: UUID, tag: str | None = None):
    httpx_mock.add_response(
        method="GET",
        url=r(f".*/inspect/{image_uuid}/$"),
        json={"uuid": str(image_uuid), "tag": tag, "created_at": "2024-01-01T12:00:00+00:00"},
        is_optional=True,
    )


def add_multiple_run_operations(
    httpx_mock: HTTPXMock,
    image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: EventResources,
    stdout_values: list[str],
):
    for stdout in stdout_values:
        op_id = str(uuid4())
        result_uuid = uuid4()

        httpx_mock.add_response(
            method="POST",
            url=r(".*/instances"),
            json={"uuid": op_id},
            is_optional=True,
        )

        add_inspect_by_uuid_response(httpx_mock, result_uuid)

        add_operation_responses(
            httpx_mock,
            op_id,
            image_uuid,
            result_uuid,
            process_state,
            resource_usage,
            stdout,
        )


@pytest.fixture
def result_image_uuid() -> UUID:
    return uuid4()


@pytest.fixture
def process_state() -> ProcessState:
    return ProcessState(
        continued=False,
        core_dump=False,
        exit_code=0,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )


@pytest.fixture
def resource_usage() -> EventResources:
    return EventResources(
        user_time_us=100_000,
        sys_time_us=100_000,
        max_rss_kb=1024,
        shared_memory=0,
        unshared_memory=0,
        swaps=0,
        minor_faults=0,
        major_faults=0,
        voluntary_ctx_switches=0,
        involuntary_ctx_switches=0,
        block_input_ops=0,
        block_output_ops=0,
        ipc_msgs_sent=0,
        ipc_msgs_received=0,
        signals_received=0,
    )


@pytest.fixture
def api_fake_run_base(
    image_uuid: UUID,
    operation_id: str,
    file_uuid: str,
    file_sha256: str,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    add_file_responses(strict_httpx, file_uuid, file_sha256)
    add_base_responses(strict_httpx, operation_id)
    return strict_httpx


@pytest.fixture
def api_fake_run(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_run_deferred(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        not_found_first=True,
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_run_with_files(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "second line\nlast line\n",
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_apply_files(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    api_fake_run_with_files: HTTPXMock,
) -> HTTPXMock:
    second_op_id = str(uuid4())
    second_result_uuid = uuid4()
    api_fake_run_with_files.add_response(
        method="POST",
        url=r(".*/instances"),
        json={"uuid": second_op_id},
        is_optional=True,
    )
    add_inspect_by_uuid_response(api_fake_run_with_files, second_result_uuid)
    add_operation_responses(
        api_fake_run_with_files,
        second_op_id,
        result_image_uuid,
        second_result_uuid,
        process_state,
        resource_usage,
        "second line\nlast line\n",
    )
    return api_fake_run_with_files


@pytest.fixture
def api_fake_run_preserve_env(
    image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    add_multiple_run_operations(
        strict_httpx,
        image_uuid,
        process_state,
        resource_usage,
        ["", "ok\n"],
    )
    return strict_httpx


@pytest.fixture
def api_fake_run_without_preserve_env(
    image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    add_multiple_run_operations(
        strict_httpx,
        image_uuid,
        process_state,
        resource_usage,
        ["", ""],
    )
    return strict_httpx


@pytest.fixture
def api_fake_run_truncated(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "a" * 50,
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_session_multiple_runs(
    image_uuid: UUID,
    file_uuid: str,
    file_sha256: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    add_file_responses(strict_httpx, file_uuid, file_sha256)

    strict_httpx.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )

    add_multiple_run_operations(
        strict_httpx,
        image_uuid,
        process_state,
        resource_usage,
        ["", "some other step\n", "some data", "final step\n"],
    )

    return strict_httpx


@pytest.fixture
def api_fake_slow_run(operation_id: str, strict_httpx: HTTPXMock) -> HTTPXMock:
    strict_httpx.add_response(
        method="POST",
        url=r(".*/instances"),
        json={"uuid": operation_id},
        is_optional=True,
    )
    strict_httpx.add_response(
        method="GET",
        url=r(f".*/operations/{operation_id}/events.*"),
        stream=SlowEventStream(),
        is_optional=True,
    )
    strict_httpx.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )
    return strict_httpx


@pytest.fixture
def api_fake_popen(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    ls_output = """total 0
drwxr-xr-x  5 root  root  180 Jan  7 10:00 .
drwxr-xr-x 18 root  root  360 Jan  7 10:00 ..
crw-rw-rw-  1 root  tty   5, 0 Jan  7 10:00 tty
crw-rw-rw-  1 root  root  1, 8 Jan  7 10:00 random
crw-rw-rw-  1 root  root  1, 3 Jan  7 10:00 null
"""

    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        create_process_state(),
        resource_usage,
        ls_output,
        "",
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_popen_error(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    error_stderr = "ls: cannot access '/totally/fake/directory': No such file or directory\n"

    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        create_process_state(exit_code=2),
        resource_usage,
        "",
        error_stderr,
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_popen_shell(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        create_process_state(),
        resource_usage,
        "Hello World\n",
        "Error message\n",
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_popen_stdin(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        create_process_state(),
        resource_usage,
        "Hello from stdin\nSecond line\n",
        "",
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_popen_communicate(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        create_process_state(),
        resource_usage,
        "test line\ntest again\n",
        "",
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_popen_env(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: EventResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        create_process_state(),
        resource_usage,
        "test_value\nanother_value\n",
        "",
    )
    return api_fake_run_base


@pytest.fixture
def api_fake_thread_pool(
    image_uuid: UUID,
    image_tag: str,
    file_uuid: str,
    file_sha256: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    from tests.unit.fixtures.images import add_inspect_by_tag_response

    add_file_responses(strict_httpx, file_uuid, file_sha256)

    for _ in range(10):
        add_inspect_by_tag_response(strict_httpx, image_tag, image_uuid)

    strict_httpx.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )

    add_multiple_run_operations(
        strict_httpx,
        image_uuid,
        process_state,
        resource_usage,
        [f"{10000 + i * 1000}\n" for i in range(10)],
    )

    return strict_httpx
