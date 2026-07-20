import httpx
import pytest

from contree_sdk._internals.utils.exception import wrap_api_exception
from contree_sdk.sdk.exceptions.api import (
    ForbiddenError,
    GoneError,
    NotFoundError,
    TooEarlyError,
    TooManyRequestsError,
    UnprocessableEntityError,
)


@pytest.mark.parametrize(
    ("status_code", "error_class"),
    [
        (403, ForbiddenError),
        (404, NotFoundError),
        (410, GoneError),
        (422, UnprocessableEntityError),
        (425, TooEarlyError),
        (429, TooManyRequestsError),
    ],
)
def test_wrap_api_exception_maps_status_codes(status_code: int, error_class: type):
    request = httpx.Request("GET", "https://fake.contree.endpoint/v1/operations")
    response = httpx.Response(status_code, request=request, json={"status": status_code, "error": "boom"})
    exc = httpx.HTTPStatusError("boom", request=request, response=response)

    assert isinstance(wrap_api_exception(exc), error_class)
