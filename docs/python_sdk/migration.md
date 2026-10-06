# Upgrade to the 0.5 session API

Version 0.5 replaces the previous SDK API. Existing applications must update their
imports and execution flow. Compatibility aliases are not provided.

Update one workflow at a time:

1. Replace client construction using {doc}`getting-started`.
2. Update result handling using {doc}`running-commands`.
3. Make persistence explicit using {doc}`sessions` and {doc}`files`.
4. Replace process-control code using {doc}`operation`.
5. Move custom behavior to the public hooks in {doc}`customization`.

Those pages contain the executable sync and async scenarios for the new API.

| Previous API                           | Replacement                                                                                                                  |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `Contree` / `ContreeSync`              | Construct a `contree_client` client, then a session.                                                                         |
| SDK image and file managers            | Use the corresponding `contree_client` methods.                                                                              |
| Image objects and `ContreeSessionSync` | `ContreeSession` for sync code; `ContreeAsyncSession` for async code.                                                        |
| `.run(...).wait().result`              | `session.run(...)` returns `InstanceResult`; await it in async code.                                                         |
| SDK result wrappers                    | Read `result.state.exit_code`, `result.stdout.as_text()`, and `result.stderr.as_bytes()`. Optional fields can be `Ellipsis`. |
| `.popen()`                             | Use `session.spawn()` and an operation context manager for subprocesses.                                                     |
| SDK auth/configuration                 | Use `contree_client` configuration, profiles, and transports.                                                                |

## Client and store ownership

The application owns the client. Close it with `with` or `async with`. A session
never closes a supplied client or store. Use matching context managers for SQLite stores and caches
so their resources close when the work is complete.

Use `SyncMemoryStore` or `SyncSQLiteStore` with a synchronous session. Use
`AsyncMemoryStore` or `AsyncSQLiteStore` with an asynchronous session. Install
`contree-sdk[async]` for the async transport and SQLite dependencies.

The default memory store lasts for one process. Pass the same `session_id` and a
SQLite store to resume a saved session. Session history contains image references;
removing a referenced server image can make an old entry unusable.

## Execution and history

`run()` and `spawn()` default to `disposable=True`. Pass `disposable=False` to retain
the result image. `run()` commits that image automatically. After `spawn()`, wait
for completion and call `session.commit_result(operation)` explicitly.

An operation records its source entry and branch at spawn time. A commit raises
`SessionConflictError` if that branch changed before the commit. Memory and SQLite
stores compare and update the branch atomically. Refresh the session from the
intended branch before starting another operation. The completed operation and its
server image remain available after a history conflict.

Concurrent commands do not automatically combine filesystem changes. Use separate
branches for independent experiments, or serialize commands that depend on previous
results. A commit to the original branch does not switch a session that has since
moved to another branch. An explicit `branch=` creates a new branch and selects it;
use `switch_branch()` before running on an existing branch.

A cancelled operation raises `InterruptedError`. An operation failure raises
`FailedOperationError`. A successful operation with a nonzero process exit code
returns its result; inspect the exit code. If waiting fails or is cancelled, the
SDK attempts to cancel the remote operation and preserves the original exception.
A `PendingRun` returned by async `run()` can be used once.

## Integrations and Dockerfile builds

Use `ContreeSandbox` for sync sessions and `ContreeAsyncSandbox` for native async
sessions. The bundled mini-swe-agent adapter still uses the removed SDK API; see
{doc}`../integrations/mini-swe-agent` for its compatibility limitation.

`ContreeDockerBuilder` and `ContreeAsyncDockerBuilder` provide Dockerfile builds
with branch-based layer reuse and memory or SQLite caches. This interpreter
implements a subset of Dockerfile instructions; see {doc}`building-images`.

## Public customization API

Use `RunRequest` with `execute()` for framework-independent execution. Extend
`prepare_request()`, `submit_request()`, or `create_operation()` instead of copying
`spawn()` internals. File I/O is injected through `file_transfer=`. Operation history
origin is available as `operation.context`.

See {doc}`customization` for the public contracts, factory hooks, and tested examples.
