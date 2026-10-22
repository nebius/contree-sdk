"""SDK payload codecs. Store does not interpret these fields."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, cast

from contree_sdk.files import StagedFile
from contree_sdk.session.models import HistoryEntry
from contree_sdk.store import JSONValue, Node
from contree_sdk.store.tree import new_node_id


def entry_from_node(session_id: str, node: Node) -> HistoryEntry:
    data = cast("dict[str, Any]", node.data)
    image = data.get("image_uuid")
    if not isinstance(image, str) or not image:
        raise ValueError("node has no resumable image")
    return HistoryEntry(
        id=node.id,
        session_id=session_id,
        image_uuid=image,
        parent_id=node.parent_id,
        kind=node.kind,
        title=data.get("title", ""),
        operation_uuid=data.get("operation_uuid"),
        exit_code=data.get("exit_code"),
        created_at=datetime.fromtimestamp(data.get("created_at", 0), timezone.utc),
        files=tuple(data.get("files", ())),
        attachments=tuple(StagedFile(**item) for item in data.get("attachments", ())),
        applied_files=tuple(data.get("applied_files", ())),
        data=data.get("user", {}),
    )


def entry_node(  # noqa: PLR0913 - encodes the existing SDK history fields
    *,
    parent_id: str | None,
    image_uuid: str | None,
    kind: str,
    created_at: float,
    title: str = "",
    operation_uuid: str | None = None,
    exit_code: int | None = None,
    files: tuple[str, ...] = (),
    attachments: tuple[StagedFile, ...] = (),
    applied_files: tuple[str, ...] = (),
    user: dict[str, JSONValue] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    node_id: str | None = None,
    payload: dict[str, JSONValue] | None = None,
) -> Node:
    data: dict[str, JSONValue] = {
        "image_uuid": image_uuid,
        "created_at": created_at,
        "title": title,
        "operation_uuid": operation_uuid,
        "exit_code": exit_code,
        "files": list(files),
        "attachments": [asdict(item) for item in attachments],
        "applied_files": list(applied_files),
        "user": user or {},
        "cwd": cwd,
        "env": dict(env or {}),
    }
    data.update(payload or {})
    return Node(id=node_id if node_id is not None else new_node_id(), parent_id=parent_id, kind=kind, data=data)


def order_entries(entries: list[HistoryEntry]) -> list[HistoryEntry]:
    """Order history without treating node identity as a sequence number.

    Returns:
        Parents before children; timestamps order independent entries.

    """
    by_id = {entry.id: entry for entry in entries}
    ordered = []
    seen = set()
    for entry in sorted(entries, key=lambda item: (item.created_at, item.id)):
        path = []
        while entry.id not in seen:
            path.append(entry)
            seen.add(entry.id)
            if entry.parent_id not in by_id:
                break
            entry = by_id[entry.parent_id]
        ordered.extend(reversed(path))
    return ordered
