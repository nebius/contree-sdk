# Tree stores

`SyncStore` and `AsyncStore` store immutable trees. Sessions, Docker builds, and
upload reuse share one Store. Helpers and direct
constructors accept it through `store=`. The Store holds references; images and files remain
on the ConTree server.

## Nodes and tree kinds

A `Node` contains `id`, `parent_id`, `kind`, and JSON-object `data`. Its generated
ID identifies a record, not a command, image, timestamp, or execution order.
Retain the same Node when retrying a write. Two executions can have equal inputs
and still produce different nodes.

A tree has one root and an immutable string `kind`. Standard consumers use
`session`, `docker-build`, `upload-cache`, and `file-sources`. Applications can
supply their own kinds. A node's kind describes its step, such as `run`, `stage`,
or `config`. Tree kinds let a CLI exclude service histories before pagination.

::::{tab} Sync

<!-- name: test_tree_store_sync -->

```python
from contree_sdk.store import Node, SyncMemoryStore

with SyncMemoryStore() as store:
    store.create_session("example", kind="session", ttl=3600)
    root = Node(parent_id=None, kind="init", data={"image_uuid": "base-image"})
    store.append("example", root)
    first = Node(parent_id=root.id, kind="run", data={"user": {"label": "first"}})
    second = Node(parent_id=root.id, kind="run", data={"user": {"label": "second"}})
    store.append("example", first)
    store.append("example", second)
    store.append("example", first)  # A repeated delivery creates no duplicate.
    assert store.get_nodes("example", (first.id, "missing")) == (first, None)
    assert len(store.list_children("example", root.id).items) == 2
    page = store.list_sessions(kind="session", limit=20)
    assert page.items[0].session_id == "example"
```

::::

::::{tab} Async

<!-- name: async test_tree_store_async -->

```python
from contree_sdk.store import AsyncMemoryStore, Node

async with AsyncMemoryStore() as store:
    await store.create_session("example", kind="session", ttl=3600)
    root = Node(parent_id=None, kind="init", data={"image_uuid": "base-image"})
    await store.append("example", root)
    first = Node(parent_id=root.id, kind="run", data={"user": {"label": "first"}})
    second = Node(parent_id=root.id, kind="run", data={"user": {"label": "second"}})
    await store.append("example", first)
    await store.append("example", second)
    await store.append("example", first)
    assert len((await store.list_children("example", root.id)).items) == 2
    page = await store.list_sessions(kind="session", limit=20)
    assert page.items[0].session_id == "example"
```

::::

## Contract

- `create_session()` creates an empty tree. Repeating it with the same kind returns
  the existing tree without renewing its TTL. A different kind raises `ValueError`.
- `append()` requires a live tree and a parent in that tree, except for its root.
  It atomically inserts one node. Equal identity and contents succeed on retry;
  changed contents or a second root raise `NodeConflictError` without overwriting.
- Reads return independent JSON values. Mutating a returned dictionary does not
  modify storage. Updating a saved node requires a new node.
- Calls are atomic across clients sharing a backend. A successful write is
  visible to subsequent reads from any client, unless deletion or expiry removes
  the tree. Concurrent calls may take either order. Separate calls are not a
  transaction. A lost response leaves the write outcome unknown; retry an append
  with the same prepared Node.
- `get_session()` returns `None` for a missing or expired tree. Reading a missing
  node or appending to a missing tree raises `ValueError`.
- `get_nodes(session_id, node_ids)` reads up to 1000 identities in one atomic
  call. The returned tuple preserves input order and duplicates. Missing nodes
  occupy `None` slots. A missing or expired tree raises `ValueError`, including
  for an empty batch. Each returned node contains independent JSON values.
- `list_sessions()`, `list_nodes()`, and `list_children()` filter before pagination
  and order by identity. `list_history()` follows parents from the specified node.
  Pass `next_cursor` with the same selection; `None` means the end. Pages are live
  reads and do not share a snapshot across calls.
- List methods request 1000 items by default. A backend can return fewer items
  with a continuation cursor to bound response size. Always follow `next_cursor`;
  a short page does not imply the end. Treat cursors as opaque positions. They
  are not authorization tokens; a remote backend must check access separately.
- TTL belongs to the whole tree. `set_session_ttl()` sets a new expiry from now.
  Reads and append do not renew it. `ttl=None` uses the implementation policy;
  the supplied Memory and SQLite implementations retain the tree until deletion.
  Zero expires immediately; negative or nonfinite TTL raises `ValueError`.
- `delete_session()` removes the tree and returns whether stored data existed,
  including expired data. It does not delete remote images or cancel operations.
  A late append cannot recreate a deleted tree. Explicit creation can reuse its
  name; use a new session ID when a new lifetime must remain distinguishable.

## Execution belongs to Session

The Store has no selected branch or shared head. Each Session keeps its own
position and local branch names. Two actors executing from the same parent add
two children. A late result keeps its captured parent even after local navigation.
Use separate Session instances for independent actors. Serialize navigation when
sharing one Session across threads. See {doc}`../branching` and {doc}`../sessions`
for selection and explicit resume.

For a live tree with root `R`, actors can append `R → A` and `R → B` in either
order. Both nodes remain available. Each actor can then extend its own node or
explicitly select a node written by another actor. Repeating the same append
adds no duplicate. Changing a node's parent or data under the same ID raises
`NodeConflictError`. This holds for any number of actors because each successful
append adds one node without changing existing nodes.

Each actor must retain its selected `(session_id, node_id)` and the prepared
Node for a retry. Use explicit `node_id` when opening a shared session;
automatic selection is not a durable actor position. Store does not merge
filesystem changes or make VM execution exactly once.

An identity cursor is not an event subscription. Concurrent inserts with IDs
before that cursor will not appear in the remaining pages. Restart enumeration
to discover them, or exchange explicit node IDs between actors. The ancestry of
a known node is stable while other actors append, so `list_history()` can page
that path without mixing branches. Deletion and expiry can still interrupt it.

Pending operations and their completions are immutable nodes too. A completion
node contains the response and retained image, so atomic append also protects
completion from partial writes. See {doc}`../detached-operations`.

Session lists operation registrations by page and reads their completion nodes
with `get_nodes()`. It does not fetch each registration again. Successful image
commits record a `staging_complete` marker in the SDK payload. Staging recovery
stops there because that image contains all staged inputs captured for the
operation. Older records remain readable through ancestry traversal. Failed or
discarded operations do not consume their source staging.

Docker searches `run` children of the selected parent and `use` nodes for FROM.
It still checks Docker hashes in the client. Large sibling sets and accumulated
FROM records can require multiple pages. Opening a session without `node_id`
still enumerates its tree to detect ambiguous continuation; pass `node_id` when
resuming a known position.

Custom backends implement this contract through `SyncStore` or `AsyncStore`.
Atomicity must cover all clients, including separate processes and connections.
An SDK-side lock alone does not meet that requirement. Memory uses SQLite's
in-memory engine; SQLite stores persist to a file. `AsyncSQLiteStore` uses
`aiosqlite`. Existing databases from earlier experimental contracts are not
migrated into these trees.

```{eval-rst}
.. automodule:: contree_sdk.store
   :members: Node, NodeId, Page, SessionInfo, NodeConflictError, SyncStore, AsyncStore, SyncMemoryStore, AsyncMemoryStore, SyncSQLiteStore, AsyncSQLiteStore
   :inherited-members:
   :undoc-members:
   :member-order: bysource
```
