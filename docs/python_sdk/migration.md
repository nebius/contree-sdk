# Upgrade to the 0.5 session API

Version 0.5 removes the previous SDK API without compatibility aliases.
Update imports, execution, and result handling as follows.

| Previous API                           | Replacement                                                                                                                                         |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Contree` / `ContreeSync`              | `create_sandbox_session` with `with` or `async with`.                                                                                               |
| SDK image and file managers            | [Image import](images.md), [build helpers](building-images.md), and [session file operations](files.md). Use the client for image listing and tags. |
| Image objects and `ContreeSessionSync` | An image UUID or tag passed to the factory; select a class with `session_type=` if needed.                                                          |
| `.run(...).wait().result`              | `session.run(...)` returns `InstanceResult`; await it in async code.                                                                                |
| SDK result wrappers                    | `result.state.exit_code`, `result.stdout.as_text()`, and `result.stderr.as_bytes()`. Optional API fields can be `Ellipsis`.                         |
| `.popen()`                             | [Operation subprocesses](operation.md), created through `session.spawn()`.                                                                          |
| SDK auth/configuration                 | `contree_client` profiles and transports; see {ref}`sandbox-connection`.                                                                            |

## Choose when to save

The factory defaults to `LazySession` or `AsyncLazySession`. Commands share a VM.
Normal context exit saves pending files; an exception discards changes since the
last snapshot. File requests through `inspect()` and `read_file()` now read the
active VM without saving or stopping it. This requires `contree-client>=0.5.1`
and a server runtime with live inspection support.

`inspect()` returns a session-bound view that selects the current source on each
request. Use `inspect_snapshot()` for a stable image view and its `image_uuid`.
Image metadata through `inspect().info()` also requires a snapshot and stops the
VM. Close file and archive streams when stopping iteration early; snapshot waits
for accepted live requests to finish.
Call `snapshot()` before switching branches or rolling back.

Select `session_type=ContreeSession` or `ContreeAsyncSession` for a separate VM
per command. `run()`, `spawn()`, `spawn_detached()`, and `RunRequest` now default
to `disposable=False`. `run()` and `execute()` commit completed results; after
`spawn()`, wait and call `commit_result()` explicitly. Pass `disposable=True`
to leave history unchanged.

Snapshots are lightweight and can run after every command. They stop the VM;
processes and memory do not survive. Unchanged files can produce the same image
UUID. See {doc}`session-model` for sync and async examples.

## Check command results

An API-successful operation can return a nonzero process exit code. The default
`ApiSuccessCommitPolicy` still commits its image. Use `ZeroExitCommitPolicy`
to save only results with exit code zero; see
[Select a commit policy](customization.md#select-a-commit-policy).

Cancellation raises `InterruptedError`; operation failure raises
`FailedOperationError`. Neither advances history. A `PendingRun` returned by
async `run()` can be consumed once. See {doc}`troubleshooting` for handling errors.

## Preserve history and manage resources

The factory closes the client and memory store it creates. Close components you
supply with `with` or `async with`; use matching sync or async implementations.
Install `contree-sdk[async]` for async transport and SQLite dependencies.

To resume after Python exits, supply a SQLite store and the same `session_id`.
History stores image references; the images must remain available on the server.
See {doc}`sessions` and {doc}`manual-sandbox`.

Commits preserve the parent selected when the operation started. Concurrent
results form sibling nodes; they do not replace each other. Branch names and the
selected node belong to each Session instance. Pass `node_id` to resume a specific
position. See [Select a late result](troubleshooting.md#advanced-select-a-late-result)
for selecting a completed result without rerunning the command.

## Update integrations and extensions

Use `ContreeSandbox` for sync executors and `ContreeAsyncSandbox` for async
executors. See {doc}`../integrations/langchain`. The mini-swe-agent 2.4.6 adapter
still uses the removed API; see {doc}`../integrations/mini-swe-agent`.

For Dockerfile builds, use {doc}`building-images`. Direct builder classes and
custom directives are covered in {doc}`advanced` and {doc}`customization`.

Move session overrides to `prepare_request()`, `submit_request()`, or
`create_operation()`. Inject file I/O with `file_transfer=`. The operation's
source history position is available through `operation.context`.
