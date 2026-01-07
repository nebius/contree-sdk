from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk._internals.models.instance import ProcessResources, ProcessState
from tests.unit.fixtures.files import add_file_responses
from tests.unit.fixtures.operations import add_base_responses, add_operation_responses
from tests.unit.fixtures.utils import r


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
