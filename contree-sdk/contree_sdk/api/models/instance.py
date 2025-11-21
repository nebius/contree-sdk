from dataclasses import dataclass, field
from enum import auto
from typing import Any

from strenum import UppercaseStrEnum

from contree_sdk.utils.objects.stream import StreamDescription


class OperationStatus(UppercaseStrEnum):
    PENDING = auto()
    EXECUTING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    ASSIGNED = auto()


@dataclass
class InstanceFileSpec:
    uuid: str
    mode: str
    uid: int
    gid: int


@dataclass(kw_only=True)
class InstanceSpawnRequest:
    command: str
    image: str
    hostname: str = "linuxkit"
    args: list[str] = field(default_factory=list)
    shell: bool = False
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = "/root"
    disposable: bool = False
    stdin: StreamDescription
    timeout: int = 60
    truncate_output_at: int = 65535
    files: dict[str, InstanceFileSpec]


@dataclass
class InstanceOperation:
    status: OperationStatus
    kind: str
    error: str | None = None
    metadata: dict[str, Any] | None = None  # todo typize
    result: dict[str, Any] | None = None
    duration: float | None = None
