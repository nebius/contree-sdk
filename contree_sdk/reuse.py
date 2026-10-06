"""Store completed upload results in typed trees using the public Store contract."""

from __future__ import annotations

import hashlib
import time
from typing import cast

from contree_sdk.store import AsyncStore, JSONValue, Node, SyncStore
from contree_sdk.store.ttl import expiration


def result_tree(namespace: str, fingerprint: str) -> str:
    return namespace + "/" + hashlib.sha256(fingerprint.encode()).hexdigest()


def result_order(node: Node) -> tuple[float, str]:
    return cast("float", node.data["recorded_at"]), node.id


def lookup_result(store: SyncStore, namespace: str, fingerprint: str) -> dict[str, JSONValue] | None:
    session_id = result_tree(namespace, fingerprint)
    if store.get_session(session_id) is None:
        return None
    candidate = None
    cursor = None
    while True:
        page = store.list_nodes(session_id, kind="result", cursor=cursor)
        for node in page.items:
            if node.data["expires_at"] is not None and cast("float", node.data["expires_at"]) <= time.time():
                continue
            if candidate is None or result_order(node) > result_order(candidate):
                candidate = node
        cursor = page.next_cursor
        if cursor is None:
            break
    return cast("dict[str, JSONValue]", candidate.data["value"]) if candidate is not None else None


def remember_result(
    store: SyncStore, namespace: str, fingerprint: str, data: dict[str, JSONValue], *, ttl: float | None = None
) -> None:
    now = time.time()
    expires_at = expiration(ttl, now)
    session_id = result_tree(namespace, fingerprint)
    if ttl == 0:
        store.delete_session(session_id)
        return
    store.create_session(session_id, kind="upload-cache", ttl=ttl)
    store.append(session_id, Node(id="root", parent_id=None, kind="input", data={"fingerprint": fingerprint}))
    store.append(
        session_id,
        Node(parent_id="root", kind="result", data={"value": data, "recorded_at": now, "expires_at": expires_at}),
    )
    store.set_session_ttl(session_id, ttl)


async def async_lookup_result(store: AsyncStore, namespace: str, fingerprint: str) -> dict[str, JSONValue] | None:
    session_id = result_tree(namespace, fingerprint)
    if await store.get_session(session_id) is None:
        return None
    candidate = None
    cursor = None
    while True:
        page = await store.list_nodes(session_id, kind="result", cursor=cursor)
        for node in page.items:
            if node.data["expires_at"] is not None and cast("float", node.data["expires_at"]) <= time.time():
                continue
            if candidate is None or result_order(node) > result_order(candidate):
                candidate = node
        cursor = page.next_cursor
        if cursor is None:
            break
    return cast("dict[str, JSONValue]", candidate.data["value"]) if candidate is not None else None


async def async_remember_result(
    store: AsyncStore, namespace: str, fingerprint: str, data: dict[str, JSONValue], *, ttl: float | None = None
) -> None:
    now = time.time()
    expires_at = expiration(ttl, now)
    session_id = result_tree(namespace, fingerprint)
    if ttl == 0:
        await store.delete_session(session_id)
        return
    await store.create_session(session_id, kind="upload-cache", ttl=ttl)
    await store.append(session_id, Node(id="root", parent_id=None, kind="input", data={"fingerprint": fingerprint}))
    await store.append(
        session_id,
        Node(parent_id="root", kind="result", data={"value": data, "recorded_at": now, "expires_at": expires_at}),
    )
    await store.set_session_ttl(session_id, ttl)
