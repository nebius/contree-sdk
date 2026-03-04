from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock

from tests.e2e.sdk.run.test_concurrency import test_parallel_imports_succeed_under_low_limits as _test_parallel_imports
from tests.e2e.sdk.run.test_concurrency import test_parallel_runs_succeed_under_low_limits as _test_parallel_runs
from tests.unit.fixtures.imports import add_import_operation
from tests.unit.fixtures.operations import add_operation_responses
from tests.unit.fixtures.runs import add_inspect_by_uuid_response
from tests.unit.fixtures.utils import r


@pytest.fixture
def api_fake_parallel_runs_with_rate_limit(
    image_uuid: UUID,
    process_state,
    resource_usage,
    api_fake_images: HTTPXMock,
) -> HTTPXMock:
    for _ in range(2):
        api_fake_images.add_response(
            method="POST",
            url=r(".*/instances"),
            status_code=429,
            json={"error": "Too Many Requests", "status": 429},
        )

    for _ in range(3):
        op_id = str(uuid4())
        result_uuid = uuid4()
        api_fake_images.add_response(
            method="POST",
            url=r(".*/instances"),
            json={"uuid": op_id},
        )
        add_inspect_by_uuid_response(api_fake_images, result_uuid)
        add_operation_responses(
            api_fake_images, op_id, image_uuid, result_uuid, process_state, resource_usage, "hello\n", ""
        )

    api_fake_images.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )

    return api_fake_images


@pytest.fixture
def api_fake_parallel_imports_with_rate_limit(strict_httpx: HTTPXMock) -> HTTPXMock:
    for _ in range(2):
        strict_httpx.add_response(
            method="POST",
            url=r(".*/images/import"),
            status_code=429,
            json={"error": "Too Many Requests", "status": 429},
        )

    for _ in range(2):
        add_import_operation(strict_httpx, str(uuid4()), uuid4())

    return strict_httpx


async def test_parallel_runs_succeed_under_low_limits(fake_contree, api_fake_parallel_runs_with_rate_limit):
    await _test_parallel_runs(fake_contree, check_timing=False)


async def test_parallel_imports_succeed_under_low_limits(fake_contree, api_fake_parallel_imports_with_rate_limit):
    await _test_parallel_imports(fake_contree, check_timing=False)
