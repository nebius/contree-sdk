"""Values exchanged by tree stores. Payloads contain JSON, never live SDK objects."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Generic, TypeAlias, TypeVar
from uuid import uuid4


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
NodeId: TypeAlias = str
T = TypeVar("T")
DEFAULT_PAGE_SIZE = 1000
MAX_NODE_BATCH_SIZE = 1000


def new_node_id() -> NodeId:
    return uuid4().hex


def encode_data(data: dict[str, JSONValue]) -> str:
    def check(value: JSONValue) -> None:
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise TypeError("JSON object keys must be strings")
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError("node data must contain JSON values")

    if not isinstance(data, dict):
        raise TypeError("node data must be a JSON object")
    check(data)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, kw_only=True)
class Node:
    parent_id: NodeId | None
    kind: str
    data: dict[str, JSONValue] = field(default_factory=dict)
    id: NodeId = field(default_factory=new_node_id)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or not isinstance(self.kind, str) or not self.kind:
            raise ValueError("node identity and kind must be nonempty strings")
        if self.parent_id is not None and (not isinstance(self.parent_id, str) or not self.parent_id):
            raise ValueError("parent must be a nonempty node identity or None")
        if self.parent_id == self.id:
            raise ValueError("node requires an identity, a kind, and a different parent")
        object.__setattr__(self, "data", json.loads(encode_data(self.data)))


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    kind: str
    created_at: float
    expires_at: float | None


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None = None


class NodeConflictError(ValueError):
    """An identity already names a different node, or the tree already has a root."""


def cursor_position(cursor: str | None, scope: tuple[object, ...], limit: int) -> str | None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if cursor is None:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        valid = value["scope"] == list(scope) and isinstance(value["position"], str)
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("cursor does not belong to this selection") from error
    if not valid:
        raise ValueError("cursor does not belong to this selection")
    return value["position"]


def next_cursor(scope: tuple[object, ...], position: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"scope": scope, "position": position}).encode()).decode()


def validate_node_ids(node_ids: tuple[NodeId, ...]) -> None:
    if len(node_ids) > MAX_NODE_BATCH_SIZE:
        raise ValueError(f"a node batch cannot exceed {MAX_NODE_BATCH_SIZE} identities")
    if any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
        raise ValueError("node identities must be nonempty strings")
