---
icon: code-branch
---

# Branching Workflows

A session's history is a DAG, not just a line: every non-disposable `.run()` appends a new entry and advances a named branch pointer (`main` by default), similar to a commit advancing a Git branch. You can branch off any point, diverge, switch back, and roll back — without losing the commits you moved away from.

## Why Branching Matters

Without ConTree, running the same operations twice (like installing packages, creating files, or compiling code) requires rebuilding the entire filesystem state from scratch each time. ConTree captures the exact filesystem state after each command, making it reproducible and allowing you to branch from that exact state.

## Chained Commits

The simplest pattern is a linear chain: keep calling `.run(disposable=False)` on the same session, and each call builds on the image the previous one produced.

````{tab} Async
```{literalinclude} ../../examples/branching/branching_simple.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/branching/branching_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

**Key Points:**

- The base commit captures a random value that would be different on each execution without ConTree
- Every subsequent commit sees the file state left by the one before it
- `session.image_uuid` always reflects the tip of the active branch

## Named Branches

For real forking — running different follow-up work from the same checkpoint without one overwriting the other — use `create_branch()`/`switch_branch()`. Each branch has its own independent tip; switching between them moves the session's live pointer without touching the other branch's history.

````{tab} Async
```{literalinclude} ../../examples/branching/branching_basic.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.ContreeAsyncSession.create_branch`, {meth}`~contree_sdk.session.ContreeAsyncSession.switch_branch`, and {meth}`~contree_sdk.session.ContreeAsyncSession.rollback`.
````

````{tab} Sync
```{literalinclude} ../../examples/branching/branching_basic_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.ContreeSession.create_branch`, {meth}`~contree_sdk.session.ContreeSession.switch_branch`, and {meth}`~contree_sdk.session.ContreeSession.rollback`.
````

`rollback(steps=1)` moves the active branch's pointer back by `steps` commits; `navigate(target)` jumps to an absolute history id or `steps` back if negative; `navigate_forward()` walks forward, picking the latest child at each branch point. `history()` returns the full DAG for a session: `(entries, branch_pointers)`.

## Persisting History

By default, a session's history lives only for the lifetime of the Python process (`SyncMemoryStore`/`AsyncMemoryStore`). Pass `store=SyncSQLiteStore(path)` (or `AsyncSQLiteStore`) to persist it to a file, so a session can be resumed — even from a different process — by passing the same `session_id` and `store` again. See {doc}`../index` for a full sessions-and-store example, and {doc}`../python_sdk/reference/store` for the `Store` API.

## Use Cases

Branching is particularly useful for:

- **Testing multiple scenarios**: Run different operations from the same starting state
- **Reproducible randomness**: Capture random/non-deterministic operations and branch from them
- **Parallel execution paths**: Execute different workflows from a common checkpoint
- **Version control for execution**: Create branches like Git for different execution flows
