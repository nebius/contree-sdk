import re
from dataclasses import asdict
from re import escape
from uuid import UUID, uuid4

import pytest
from httpx import QueryParams
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk.api.models.instance import (
    InstanceOperationMetadata,
    InstanceOperationResult,
    ProcessExecutionResult,
    ProcessResources,
    ProcessState,
)
from contree_sdk.api.models.operation import OperationKind, OperationModel, OperationStatus
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.utils.codecs import io_encode
from contree_sdk.utils.objects.stream import StreamDescription, StreamEncoding


@pytest.fixture()
def fake_contree_config() -> ContreeConfig:
    return ContreeConfig(token="fake-token", base_url="https://fake.contree.endpoint")


@pytest.fixture()
def fake_contree(fake_contree_config: ContreeConfig) -> Contree:
    return Contree(config=fake_contree_config)


@pytest.fixture()
def fake_contree_s(fake_contree_config: ContreeConfig) -> ContreeSync:
    return ContreeSync(config=fake_contree_config)


@pytest.fixture()
def strict_httpx(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.reset()
    httpx_mock.strict_responses = True
    return httpx_mock


@pytest.fixture()
def image_uuid() -> UUID:
    return uuid4()


@pytest.fixture()
def result_image_uuid() -> UUID:
    return uuid4()


@pytest.fixture()
def operation_id() -> str:
    return str(uuid4())


@pytest.fixture()
def file_uuid() -> str:
    return str(uuid4())


@pytest.fixture()
def file_sha256() -> str:
    return "1c338c24f4a82e6dc440204d8d6a08058a58136d3e01b4f7aa0f7588b51ba197"


@pytest.fixture()
def image_tag() -> str:
    return "busybox:latest"


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


r = re.compile


def url(path: str, params: dict = None) -> re.Pattern:
    if params is not None:
        path += escape("?" + str(QueryParams(params)))
    return r(".*" + path)


def add_file_responses(httpx_mock: HTTPXMock, file_uuid: str, file_sha256: str):
    httpx_mock.add_response(
        method="GET",
        url=r(".*/files\\?sha256=.*"),
        status_code=404,
        json={"error": "File not found", "status": 404},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="POST",
        url=r(".*/files"),
        json={"uuid": file_uuid, "sha256": file_sha256},
        is_optional=True,
    )


def add_base_responses(httpx_mock: HTTPXMock, operation_id: str):
    httpx_mock.add_response(
        method="POST",
        url=r(".*/instances"),
        json={"uuid": operation_id},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=r(".*/inspect/.*"),
        json={"uuid": str(uuid4()), "tag": None, "created_at": "2024-01-01T12:00:00+00:00"},
        is_optional=True,
    )


def create_operation_model(
    image_uuid: UUID,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    stdout_content: str,
    status: OperationStatus,
    duration: float = 0.0,
) -> OperationModel:
    execution_result = ProcessExecutionResult(
        stdout=io_encode(stdout_content, StreamEncoding.base64),
        stderr=io_encode("this is stderr\n", StreamEncoding.base64),
        state=process_state,
        resources=resource_usage,
    )

    metadata = InstanceOperationMetadata(
        args=[],
        command="",
        cwd="/",
        disposable=True,
        env={},
        files={},
        hostname="",
        image=str(image_uuid),
        shell=True,
        stdin=StreamDescription(value="", encoding=StreamEncoding.ascii),
        timeout=60,
        truncate_output_at=65535,
        result=execution_result,
    )

    return OperationModel(
        kind=OperationKind.INSTANCE,
        status=status,
        duration=duration,
        metadata=metadata,
        result=InstanceOperationResult(image=str(result_image_uuid), tag=None),
    )


def add_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    image_uuid: UUID,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    stdout_content: str = "my input\nthis is stdout\n",
):
    pending_op = create_operation_model(
        image_uuid, result_image_uuid, process_state, resource_usage, stdout_content, OperationStatus.PENDING
    )
    success_op = create_operation_model(
        image_uuid, result_image_uuid, process_state, resource_usage, stdout_content, OperationStatus.SUCCESS, 0.5
    )

    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}"),
        json=asdict(pending_op),
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}"),
        json=asdict(success_op),
        is_optional=True,
    )


@pytest.fixture()
def api_fake_images(image_uuid: UUID, image_tag: str, strict_httpx: HTTPXMock) -> HTTPXMock:
    image_dict = {"uuid": str(image_uuid), "tag": image_tag, "created_at": "2024-01-01T12:00:00+00:00"}
    strict_httpx.add_response(
        method="GET",
        url=r(".*/images"),
        json={
            "images": [
                image_dict,
            ]
        },
        is_optional=True,
    )
    strict_httpx.add_response(
        method="GET",
        url=r(f".*/inspect/{image_uuid}"),
        json=image_dict,
        is_optional=True,
    )
    strict_httpx.add_response(
        method="GET",
        url=url("/inspect", params={"tag": image_tag}),
        json=image_dict,
        is_optional=True,
    )
    strict_httpx.add_response(
        method="GET",
        url=r(".*/inspect/.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    strict_httpx.add_response(
        method="GET",
        url=r(r".*/inspect\?tag=.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    return strict_httpx


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
def fake_image(fake_contree: Contree, image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock) -> ContreeImage:
    return ContreeImage(client=fake_contree, uuid=image_uuid, tag=image_tag)


@pytest.fixture()
def fake_image_s(
    fake_contree_s: ContreeSync, image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock
) -> ContreeImageSync:
    return ContreeImageSync(client=fake_contree_s, uuid=image_uuid, tag=image_tag)
