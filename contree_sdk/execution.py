"""Public command values and execution contracts for integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType

from contree_client.models import InstanceNetworking, InstanceResourcesLimits, InstanceResult

from contree_sdk.files import InputSource, RunFiles


@dataclass(frozen=True, kw_only=True)
class RunRequest:
    """Command configuration passed through the session's public extension hooks.

    Use ``dataclasses.replace`` to change a request. Arguments and environment
    are copied at construction. File sources and stdin remain caller-owned.
    Exactly one of ``command`` and ``shell`` must be supplied.
    """

    command: str | None = None
    shell: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    cwd: str | None = None
    stdin: InputSource | None = None
    stdin_open: bool = False
    files: RunFiles = None
    timeout: float | timedelta | None = None
    disposable: bool = True
    truncate_output_at: int | None = None
    preserve_env: bool = False
    hostname: str | None = None
    uid: int | None = None
    gid: int | None = None
    resources_limits: InstanceResourcesLimits | None = None
    networking: InstanceNetworking | None = None

    def __post_init__(self) -> None:
        if (self.command is None) == (self.shell is None):
            raise ValueError("provide exactly one of command or shell")
        object.__setattr__(self, "args", tuple(self.args))
        if self.env is not None:
            object.__setattr__(self, "env", MappingProxyType(dict(self.env)))

    @property
    def title(self) -> str:
        return self.shell if self.shell is not None else str(self.command)

    @property
    def timeout_seconds(self) -> float | None:
        return self.timeout.total_seconds() if isinstance(self.timeout, timedelta) else self.timeout


@dataclass(frozen=True)
class OperationContext:
    """The effective request and history position captured before remote execution."""

    request: RunRequest
    session_id: str
    image_uuid: str
    parent_id: int | None
    branch: str | None
    files: tuple[str, ...] = ()


class SyncExecutor(ABC):
    """Execution and file access required by synchronous framework adapters.

    Implementations own their lifecycle. Adapters do not close executors.
    Successful execution returns the client's InstanceResult, including nonzero
    exit codes. read_file returns exact bytes or raises a client API exception.
    """

    session_id: str

    @abstractmethod
    def execute(self, request: RunRequest) -> InstanceResult: ...

    @abstractmethod
    def read_file(self, path: str) -> bytes: ...


class AsyncExecutor(ABC):
    """Native asynchronous execution and file access for framework adapters."""

    session_id: str

    @abstractmethod
    async def execute(self, request: RunRequest) -> InstanceResult: ...

    @abstractmethod
    async def read_file(self, path: str) -> bytes: ...
