"""Public lifecycle contracts for operation and subprocess implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Iterable, Iterator
from typing import IO

from contree_client.models import InstanceResult, OperationEvent, OperationResponse

from contree_sdk.compat import Self
from contree_sdk.execution import OperationContext
from contree_sdk.session.stdin import DEFAULT_STDIN_CHUNK_SIZE, StdinResult


OperationObserver = Callable[[OperationEvent | None, Exception | None], None]
AsyncOperationObserver = Callable[[OperationEvent | None, Exception | None], Awaitable[None]]


class SubprocessContract(ABC):
    """Waitable event stream for one subprocess. Iteration and wait share completion state."""

    spid: int

    @abstractmethod
    def __iter__(self) -> Iterator[OperationEvent]: ...

    @abstractmethod
    def wait(self, *, timeout: float | None = None) -> InstanceResult: ...

    @abstractmethod
    def pipe_to(
        self, *, stdout: IO[str] | IO[bytes] | None = None, stderr: IO[str] | IO[bytes] | None = None
    ) -> InstanceResult: ...


class AsyncSubprocessContract(ABC):
    """Waitable event stream for one subprocess. Iteration and wait share completion state."""

    spid: int

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[OperationEvent]: ...

    @abstractmethod
    async def wait(self, *, timeout: float | None = None) -> InstanceResult: ...

    @abstractmethod
    async def pipe_to(
        self, *, stdout: IO[str] | IO[bytes] | None = None, stderr: IO[str] | IO[bytes] | None = None
    ) -> InstanceResult: ...

    def __await__(self):
        return self.wait().__await__()


class OperationContract(ABC):
    """An operation lifecycle. wait stores response before returning; cleanup preserves primary errors."""

    uuid: str
    context: OperationContext | None
    response: OperationResponse | None

    def add_observer(self, observer: OperationObserver) -> None:
        """Register an observer before starting the shared operation reader.

        A None event marks EOF, with an optional stream error. Observers must
        not consume events or wait for this operation. Implementations without
        this optional facility reject registration.
        """
        raise NotImplementedError("this operation does not support event observers")

    @abstractmethod
    def events(
        self, *, since: int | None = None, spid: int | None = None, timeout: float | None = None
    ) -> Iterator[OperationEvent]: ...

    @abstractmethod
    def status(self, *, inflight: bool = False) -> OperationResponse: ...

    @abstractmethod
    def send_stdin(self, data: str | bytes, *, spid: int = 1, close: bool = True) -> None: ...

    @abstractmethod
    def pipe_stdin(
        self,
        chunks: Iterable[str | bytes],
        *,
        spid: int = 1,
        close: bool = True,
        chunk_size: int = DEFAULT_STDIN_CHUNK_SIZE,
    ) -> StdinResult: ...

    @abstractmethod
    def signal(self, sig: str | None = None, *, spid: int = 1) -> None: ...

    @abstractmethod
    def cancel(self) -> None: ...

    @abstractmethod
    def wait(self, *, timeout: float | None = None) -> InstanceResult: ...

    @abstractmethod
    def __enter__(self) -> Self: ...

    @abstractmethod
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    @abstractmethod
    def run(
        self,
        command: str,
        *,
        shell: bool = False,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        uid: int | None = None,
        gid: int | None = None,
        stdin: str | bytes | None = None,
        stdin_open: bool = False,
        truncate_output_at: int | None = None,
    ) -> SubprocessContract: ...

    @abstractmethod
    def shutdown(self) -> None: ...


class AsyncOperationContract(ABC):
    """An operation lifecycle. wait stores response before returning; cleanup preserves primary errors."""

    uuid: str
    context: OperationContext | None
    response: OperationResponse | None

    def add_observer(self, observer: AsyncOperationObserver) -> None:
        """Register an observer before starting the shared operation reader.

        A None event marks EOF, with an optional stream error. Observers must
        not consume events or wait for this operation. Implementations without
        this optional facility reject registration.
        """
        raise NotImplementedError("this operation does not support event observers")

    @abstractmethod
    def events(
        self, *, since: int | None = None, spid: int | None = None, timeout: float | None = None
    ) -> AsyncIterator[OperationEvent]: ...

    @abstractmethod
    async def status(self, *, inflight: bool = False) -> OperationResponse: ...

    @abstractmethod
    async def send_stdin(self, data: str | bytes, *, spid: int = 1, close: bool = True) -> None: ...

    @abstractmethod
    async def pipe_stdin(
        self,
        chunks: AsyncIterable[str | bytes],
        *,
        spid: int = 1,
        close: bool = True,
        chunk_size: int = DEFAULT_STDIN_CHUNK_SIZE,
    ) -> StdinResult: ...

    @abstractmethod
    async def signal(self, sig: str | None = None, *, spid: int = 1) -> None: ...

    @abstractmethod
    async def cancel(self) -> None: ...

    @abstractmethod
    async def wait(self, *, timeout: float | None = None) -> InstanceResult: ...

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    @abstractmethod
    async def run(
        self,
        command: str,
        *,
        shell: bool = False,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        uid: int | None = None,
        gid: int | None = None,
        stdin: str | bytes | None = None,
        stdin_open: bool = False,
        truncate_output_at: int | None = None,
    ) -> AsyncSubprocessContract: ...

    @abstractmethod
    async def shutdown(self) -> None: ...
