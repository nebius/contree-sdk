"""Typed views of saved session history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from contree_sdk.files import StagedFile
from contree_sdk.store.tree import JSONValue


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    session_id: str
    image_uuid: str
    parent_id: str | None
    kind: str
    title: str
    operation_uuid: str | None
    exit_code: int | None
    created_at: datetime
    files: tuple[str, ...] = ()
    attachments: tuple[StagedFile, ...] = ()
    applied_files: tuple[str, ...] = ()
    data: dict[str, JSONValue] = field(default_factory=dict)
