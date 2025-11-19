from dataclasses import dataclass, field


@dataclass(frozen=True, kw_only=True)
class RunRequest:
    command: str | None = None
    args: list[str] | None = None
    shell: bool | None = None
    env: dict[str, str] = field(default_factory=dict)
    cwd: str

    tag: str | None = None  # tag to be assigned to result
    stdin: str | None = None  # todo add support for IO objects
