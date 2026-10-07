"""Durable operation records, independent of live handles and input streams."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

from contree_sdk.store.models import StagedFile


@dataclass(frozen=True, kw_only=True)
class OperationRecord:
    """A registered operation and its first atomically completed outcome.

    request_json holds the effective command, excluding source streams. A non-null
    response_json marks completion, including failed, cancelled, and discarded
    results. history_id is set only when that completion retained an image.
    """

    uuid: str
    session_id: str
    image_uuid: str
    parent_id: int
    branch: str
    title: str
    disposable: bool
    request_json: str
    endpoint: str = ""
    files: tuple[str, ...] = ()
    attachments: tuple[StagedFile, ...] = ()
    response_json: str | None = None
    history_id: int | None = None

    def __post_init__(self) -> None:
        if not self.uuid or not self.session_id or not self.image_uuid or not self.branch:
            raise ValueError("registered operations require UUID, session, image, and branch")
        if self.parent_id <= 0:
            raise ValueError("registered operations require a source history entry")
        if not isinstance(json.loads(self.request_json), dict):
            raise TypeError("operation request must be a JSON object")
        if self.response_json is not None and not isinstance(json.loads(self.response_json), dict):
            raise TypeError("operation response must be a JSON object")
        if self.history_id is not None and (self.history_id <= 0 or self.response_json is None):
            raise ValueError("completed history requires a response and a positive entry ID")
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "attachments", tuple(self.attachments))

    @property
    def pending(self) -> bool:
        return self.response_json is None

    def registration(self) -> OperationRecord:
        return replace(self, response_json=None, history_id=None)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> OperationRecord:
        data = json.loads(payload)
        data["attachments"] = tuple(StagedFile(**item) for item in data.get("attachments", ()))
        return cls(**data)


def validate_registration(record: OperationRecord, existing: OperationRecord | None) -> OperationRecord:
    if not record.pending or record.history_id is not None:
        raise ValueError("register an operation before completing it")
    if existing is not None and existing.registration() != record:
        raise ValueError("operation UUID is already registered with another context")
    return record if existing is None else existing
