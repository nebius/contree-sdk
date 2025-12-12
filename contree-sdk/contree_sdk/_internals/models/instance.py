from dataclasses import dataclass, field
from typing import Any

from contree_sdk.utils.objects.stream import StreamDescription


@dataclass
class ProcessResources:
    block_input: int
    block_output: int
    cost: float
    elapsed_time: float
    involuntary_switches: int
    max_rss: int
    monotonic_time: float
    page_faults: int
    page_faults_io: int
    shared_memory: int
    signals: int
    swaps: int
    system_cpu_time: float
    unshared_memory: int
    user_cpu_time: float
    voluntary_switches: int


@dataclass
class ProcessState:
    continued: bool
    core_dump: bool
    exit_code: int
    pid: int
    signal: int
    stopped: bool
    timed_out: bool


@dataclass
class ProcessExecutionResult:
    resources: ProcessResources
    state: ProcessState
    stderr: StreamDescription
    stdout: StreamDescription


@dataclass
class InstanceOperationMetadata:
    args: list[str]
    command: str
    cwd: str
    disposable: bool
    env: dict[str, str]
    files: dict[str, Any]
    hostname: str
    image: str
    result: ProcessExecutionResult | None
    shell: bool
    stdin: StreamDescription
    timeout: int
    truncate_output_at: int


@dataclass
class InstanceOperationResult:
    image: str | None
    tag: str | None


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
