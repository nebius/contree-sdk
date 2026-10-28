"""Durable operation records, independent of live handles and input streams."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, cast

from contree_sdk.files import StagedFile
from contree_sdk.store import JSONValue


@dataclass(frozen=True, kw_only=True)
class OperationRecord:
    """A registered operation and its first atomically completed outcome.

    request holds the effective command, excluding source streams. A non-null
    response marks completion, including failed, cancelled, and discarded
    results. history_id is set only when that completion retained an image.
    """

    uuid: str
    session_id: str
    image_uuid: str
    parent_id: str
    branch: str
    title: str
    disposable: bool
    request: dict[str, JSONValue]
    endpoint: str = ""
    created_at: float = 0.0
    node_id: str = ""
    session_cwd: str | None = None
    session_env: dict[str, str] = field(default_factory=dict)
    files: tuple[str, ...] = ()
    attachments: tuple[StagedFile, ...] = ()
    response: dict[str, JSONValue] | None = None
    history_id: str | None = None

    def __post_init__(self) -> None:
        if not self.uuid or not self.session_id or not self.image_uuid or not self.branch:
            raise ValueError("registered operations require UUID, session, image, and branch")
        if not self.parent_id:
            raise ValueError("registered operations require a source history entry")
        if not isinstance(self.request, dict):
            raise TypeError("operation request must be a JSON object")
        if self.response is not None and not isinstance(self.response, dict):
            raise TypeError("operation response must be a JSON object")
        if self.history_id is not None and (not self.history_id or self.response is None):
            raise ValueError("completed history requires a response and a nonempty entry ID")
        object.__setattr__(self, "request", deepcopy(self.request))
        object.__setattr__(self, "response", deepcopy(self.response))
        object.__setattr__(self, "session_env", dict(self.session_env))
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "attachments", tuple(self.attachments))

    @property
    def pending(self) -> bool:
        return self.response is None

    def to_dict(self) -> dict[str, JSONValue]:
        data = asdict(self)
        data["files"] = list(self.files)
        data["attachments"] = [asdict(item) for item in self.attachments]
        return data

    @classmethod
    def from_dict(cls, payload: dict[str, JSONValue]) -> OperationRecord:
        data = cast("dict[str, Any]", dict(payload))
        data["attachments"] = tuple(StagedFile(**item) for item in data.get("attachments", ()))
        return cls(**data)
