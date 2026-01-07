from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk._internals.models.instance import ProcessResources, ProcessState
from tests.unit.fixtures.files import add_file_responses
from tests.unit.fixtures.operations import add_base_responses, add_operation_responses
from tests.unit.fixtures.utils import r, url


@pytest.fixture()
def result_image_uuid() -> UUID:
    return uuid4()


@pytest.fixture()
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


@pytest.fixture()
def resource_usage() -> ProcessResources:
    return ProcessResources(
        block_input=0,
        block_output=0,
        cost=0.0,
        elapsed_time=0.5,
        involuntary_switches=0,
        max_rss=1024,
        monotonic_time=0.5,
        page_faults=0,
        page_faults_io=0,
        shared_memory=0,
        signals=0,
        swaps=0,
        system_cpu_time=0.1,
        unshared_memory=0,
        user_cpu_time=0.1,
        voluntary_switches=0,
    )


@pytest.fixture()
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


@pytest.fixture()
def api_fake_run(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: ProcessResources,
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


@pytest.fixture()
def api_fake_run_with_files(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: ProcessResources,
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


@pytest.fixture()
def api_fake_session_multiple_runs(
    image_uuid: UUID,
    file_uuid: str,
    file_sha256: str,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    add_file_responses(strict_httpx, file_uuid, file_sha256)

    strict_httpx.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )

    for stdout in ["", "some other step\n", "some data"]:
        op_id = str(uuid4())
        result_uuid = uuid4()

        strict_httpx.add_response(
            method="POST",
            url=r(".*/instances"),
            json={"uuid": op_id},
            is_optional=True,
        )

        strict_httpx.add_response(
            method="GET",
            url=r(f".*/inspect/{result_uuid}$"),
            json={"uuid": str(result_uuid), "tag": None, "created_at": "2024-01-01T12:00:00+00:00"},
            is_optional=True,
        )

        add_operation_responses(
            strict_httpx,
            op_id,
            image_uuid,
            result_uuid,
            process_state,
            resource_usage,
            stdout,
        )

    return strict_httpx


@pytest.fixture()
def api_fake_popen(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: ProcessResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    process_state = ProcessState(
        continued=False,
        core_dump=False,
        exit_code=0,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )

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
        process_state,
        resource_usage,
        ls_output,
        "",
    )
    return api_fake_run_base


@pytest.fixture()
def api_fake_popen_error(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: ProcessResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    process_state = ProcessState(
        continued=False,
        core_dump=False,
        exit_code=2,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )

    error_stderr = "ls: cannot access '/totally/fake/directory': No such file or directory\n"

    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "",
        error_stderr,
    )
    return api_fake_run_base


@pytest.fixture()
def api_fake_popen_shell(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: ProcessResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    process_state = ProcessState(
        continued=False,
        core_dump=False,
        exit_code=0,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )

    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "Hello World\n",
        "Error message\n",
    )
    return api_fake_run_base


@pytest.fixture()
def api_fake_popen_stdin(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: ProcessResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    process_state = ProcessState(
        continued=False,
        core_dump=False,
        exit_code=0,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )

    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "Hello from stdin\nSecond line\n",
        "",
    )
    return api_fake_run_base


@pytest.fixture()
def api_fake_popen_communicate(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: ProcessResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    process_state = ProcessState(
        continued=False,
        core_dump=False,
        exit_code=0,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )

    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "test line\ntest again\n",
        "",
    )
    return api_fake_run_base


@pytest.fixture()
def api_fake_popen_env(
    image_uuid: UUID,
    result_image_uuid: UUID,
    operation_id: str,
    resource_usage: ProcessResources,
    api_fake_run_base: HTTPXMock,
) -> HTTPXMock:
    process_state = ProcessState(
        continued=False,
        core_dump=False,
        exit_code=0,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )

    add_operation_responses(
        api_fake_run_base,
        operation_id,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "test_value\nanother_value\n",
        "",
    )
    return api_fake_run_base


@pytest.fixture()
def api_fake_thread_pool(
    image_uuid: UUID,
    image_tag: str,
    file_uuid: str,
    file_sha256: str,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    add_file_responses(strict_httpx, file_uuid, file_sha256)

    for _ in range(10):
        strict_httpx.add_response(
            method="GET",
            url=url("/inspect", params={"tag": image_tag}),
            json={"uuid": str(image_uuid), "tag": image_tag, "created_at": "2024-01-01T12:00:00+00:00"},
            is_optional=True,
        )

    strict_httpx.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )

    for i in range(10):
        op_id = str(uuid4())
        result_uuid = uuid4()
        random_number = str(10000 + i * 1000)

        strict_httpx.add_response(
            method="POST",
            url=r(".*/instances"),
            json={"uuid": op_id},
            is_optional=True,
        )

        strict_httpx.add_response(
            method="GET",
            url=r(f".*/inspect/{result_uuid}$"),
            json={"uuid": str(result_uuid), "tag": None, "created_at": "2024-01-01T12:00:00+00:00"},
            is_optional=True,
        )

        add_operation_responses(
            strict_httpx,
            op_id,
            image_uuid,
            result_uuid,
            process_state,
            resource_usage,
            f"{random_number}\n",
            "",
        )

    return strict_httpx
