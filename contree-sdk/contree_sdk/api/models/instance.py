from dataclasses import dataclass, field
from enum import auto
from typing import Any, Literal

from strenum import UppercaseStrEnum


class OperationStatus(UppercaseStrEnum):
    PENDING = auto()
    EXECUTING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    ASSIGNED = auto()


@dataclass
class StreamModel:
    value: str
    encoding: Literal["base64"] = "ascii"
    truncated: bool = False


@dataclass
class InstanceFileSpec:
    uuid: str
    mode: str = "0644"
    uid: int = 0
    gid: int = 0


@dataclass
class InstanceSpawnRequest:
    command: str
    image: str
    hostname: str = "linuxkit"
    args: list[str] = field(default_factory=list)
    shell: bool = False
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = "/root"
    disposable: bool = False
    stdin: StreamModel = field(default_factory=lambda: StreamModel(value=""))
    timeout: int = 60
    truncate_output_at: int = 65535
    files: dict[str, InstanceFileSpec] = field(default_factory=dict)


@dataclass
class InstanceOperation:
    status: OperationStatus
    kind: str
    error: str | None = None
    metadata: dict[str, Any] | None = None  # todo typize
    result: dict[str, Any] | None = None
    duration: float | None = None
