from __future__ import annotations

from contextlib import contextmanager
from json import JSONDecodeError

from httpx import HTTPError, HTTPStatusError, Response, TimeoutException, TransportError

from contree_sdk.sdk.exceptions import (
    ApiStatusCodeError,
    ApiTimeoutError,
    ContreeError,
    ContreeTransportError,
    ForbiddenError,
    NotFoundError,
    UnknownContreeError,
)
from contree_sdk.sdk.exceptions.api import RequestInfo, ResponseInfo, TooManyRequestsError


# for now, it works with httpx errors
# when be implementing multi transport support, we should change it to some other class
def wrap_api_exception(exc: HTTPError, kwargs: dict | None = None) -> ContreeError:
    request_info = RequestInfo(
        url=str(exc.request.url),
        method=exc.request.method,
    )
    response = getattr(exc, "response", None)
    response_info = None
    if isinstance(response, Response):
        response_info = ResponseInfo(
            headers=dict(response.headers),
        )

    if isinstance(exc, TimeoutException):
        return ApiTimeoutError(
            timeout_type=str(exc.__class__.__name__).lower().replace("timeout", ""),
            request=request_info,
            response=response_info,
        )

    if isinstance(exc, TransportError):
        return ContreeTransportError(_raw=exc, error=str(exc), request=request_info, response=response_info)

    if isinstance(exc, HTTPStatusError):
        response = exc.response
        try:
            data = response.json()
        except JSONDecodeError:
            data = {"status": response.status_code, "error": response.text}
        class_ = ApiStatusCodeError
        if response.status_code == 404:
            class_ = NotFoundError
        elif response.status_code == 403:
            class_ = ForbiddenError
        elif response.status_code == 429:
            class_ = TooManyRequestsError
        return class_(**data, request=request_info, response=response_info)

    return UnknownContreeError(exception=exc)


@contextmanager
def wrap_api_call():
    try:
        yield
    except HTTPError as exc:
        raise wrap_api_exception(exc).with_traceback(exc.__traceback__) from exc
