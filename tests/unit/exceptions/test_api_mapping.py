import httpx
import pytest
from contree_client import exceptions as transport_exceptions
from contree_client.httpx import ContreeClient as HttpxTransport
from contree_client.runtime import ResponseData, error_for_response

from contree_sdk._internals.utils.exception import wrap_api_exception
from contree_sdk.sdk.exceptions import UnknownContreeError
from contree_sdk.sdk.exceptions.api import (
    ApiStatusCodeError,
    ApiTimeoutError,
    ContreeTransportError,
    EventStreamInterruptedError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    TooEarlyError,
    TooManyRequestsError,
    UnprocessableEntityError,
)


@pytest.fixture
def transport() -> HttpxTransport:
    return HttpxTransport("fake-token", base_url="https://fake.contree.endpoint")


@pytest.mark.parametrize(
    ("status_code", "error_class"),
    [
        (400, ApiStatusCodeError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (410, GoneError),
        (422, UnprocessableEntityError),
        (425, TooEarlyError),
        (429, TooManyRequestsError),
        (500, ApiStatusCodeError),
    ],
)
def test_wrap_api_exception_maps_status_codes(
    status_code: int, error_class: type[ApiStatusCodeError], transport: HttpxTransport
):
    exc = transport_exceptions.ContreeAPIError(status_code, "boom")

    wrapped = wrap_api_exception(exc, transport)

    assert isinstance(wrapped, error_class)
    assert wrapped.status == status_code
    assert wrapped.error == "boom"


def test_wrap_api_exception_uses_response_payload(transport: HttpxTransport):
    response = ResponseData(status=404, headers={}, body=b'{"status": 404, "error": "not here"}')

    wrapped = wrap_api_exception(error_for_response(response), transport)

    assert isinstance(wrapped, NotFoundError)
    assert wrapped.error == "not here"


@pytest.mark.parametrize(
    "exc",
    [
        transport_exceptions.SSEStreamError("stream broke"),
        transport_exceptions.DecompressionError("truncated gzip"),
    ],
)
def test_wrap_api_exception_maps_stream_errors(exc: Exception, transport: HttpxTransport):
    assert isinstance(wrap_api_exception(exc, transport), EventStreamInterruptedError)


@pytest.mark.parametrize(
    ("exc", "timeout_type"),
    [
        (httpx.ConnectTimeout("slow"), "connect"),
        (httpx.ReadTimeout("slow"), "read"),
        (httpx.PoolTimeout("slow"), "pool"),
    ],
)
def test_wrap_api_exception_maps_timeouts(exc: Exception, timeout_type: str, transport: HttpxTransport):
    wrapped = wrap_api_exception(exc, transport)

    assert isinstance(wrapped, ApiTimeoutError)
    assert wrapped.timeout_type == timeout_type


def test_wrap_api_exception_maps_transport_errors(transport: HttpxTransport):
    exc = httpx.ConnectError("no route to host")

    wrapped = wrap_api_exception(exc, transport)

    assert isinstance(wrapped, ContreeTransportError)
    assert wrapped._raw is exc


def test_wrap_api_exception_maps_unexpected_client_errors(transport: HttpxTransport):
    exc = transport_exceptions.ContreeError("unexpected")

    assert isinstance(wrap_api_exception(exc, transport), UnknownContreeError)


def test_wrap_api_exception_passes_foreign_errors_through(transport: HttpxTransport):
    assert wrap_api_exception(ValueError("not transport related"), transport) is None
