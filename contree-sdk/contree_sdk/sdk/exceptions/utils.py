from json import JSONDecodeError

from httpx import HTTPError, HTTPStatusError, TimeoutException, TransportError

from contree_sdk.sdk.exceptions import (
    ApiStatusCodeError,
    ApiTimeoutError,
    ContreeException,
    ContreeTransportError,
    ForbiddenError,
    NotFoundError,
    UnknownContreeException,
)


# for now, it works with httpx errors
# when be implementing
def wrap_api_exception(exc: HTTPError, kwargs: dict | None = None) -> ContreeException:
    if isinstance(exc, TimeoutException):
        return ApiTimeoutError()

    if isinstance(exc, TransportError):
        return ContreeTransportError(_raw=exc, error=str(exc))

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
        return class_(**data)

    return UnknownContreeException(exception=exc)
