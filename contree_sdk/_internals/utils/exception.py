from __future__ import annotations

import http.client
from contextlib import contextmanager

from contree_client import exceptions as transport_exceptions
from contree_client.base import ContreeClientBase

from contree_sdk.sdk.exceptions import (
    ApiStatusCodeError,
    ApiTimeoutError,
    ContreeError,
    ContreeTransportError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    TooEarlyError,
    UnknownContreeError,
    UnprocessableEntityError,
)
from contree_sdk.sdk.exceptions.api import EventStreamInterruptedError, TooManyRequestsError


_STATUS_ERROR_CLASSES: dict[int, type[ApiStatusCodeError]] = {
    403: ForbiddenError,
    404: NotFoundError,
    410: GoneError,
    422: UnprocessableEntityError,
    425: TooEarlyError,
    429: TooManyRequestsError,
}


def _timeout_errors(transport: ContreeClientBase) -> tuple[type[BaseException], ...]:
    return tuple(error for error in transport.nonretryable_errors if not issubclass(error, http.client.InvalidURL))


def wrap_api_exception(exc: Exception, transport: ContreeClientBase) -> ContreeError | None:
    """Translate a contree-client or transport error into an SDK exception.

    Transport-level classification relies on the ``retryable_errors`` and
    ``nonretryable_errors`` tuples every contree-client backend declares, so
    no backend package is imported here.

    Returns:
        The matching SDK exception, or None for exceptions that are not
        transport-related and must propagate unchanged.

    """
    if isinstance(exc, transport_exceptions.ContreeAPIError):
        class_ = _STATUS_ERROR_CLASSES.get(exc.status, ApiStatusCodeError)
        return class_(status=exc.status, error=str(exc.error))
    if isinstance(exc, (transport_exceptions.SSEStreamError, transport_exceptions.DecompressionError)):
        return EventStreamInterruptedError(error=str(exc))
    if isinstance(exc, transport_exceptions.ContreeError):
        return UnknownContreeError(exception=exc)
    if isinstance(exc, _timeout_errors(transport)):
        return ApiTimeoutError(timeout_type=type(exc).__name__.lower().replace("timeout", "") or None)
    if isinstance(exc, transport.retryable_errors):
        return ContreeTransportError(_raw=exc, error=str(exc))
    return None


@contextmanager
def wrap_api_call(transport: ContreeClientBase):
    try:
        yield
    except Exception as exc:
        wrapped = wrap_api_exception(exc, transport)
        if wrapped is None:
            raise
        raise wrapped.with_traceback(exc.__traceback__) from exc
