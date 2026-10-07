# Choose an execution layer

Start with `ContreeSession` for independent commands that share saved files.
Choose `LazySession` when several commands need the same running processes before
a snapshot. Use `Operation` directly when your application must control a single
VM, its subprocesses, and its event stream.

## Execution and persistence

| Component                                | When a VM starts                                                                                                         | When files are saved                                                                                                    | What happens to processes                                                                          | Who releases resources                                                                                                                     |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `ContreeSession` / `ContreeAsyncSession` | Each `run`, `execute`, or `spawn` submits an operation.                                                                  | Non-disposable `run`/`execute` commits after API success. For `spawn`, call `commit_result` after waiting.              | Each operation has a separate process lifetime. A saved image does not preserve running processes. | The session closes handles created by `run`/`execute`/`wait_operation`. The caller owns spawned handles, client, and store.                |
| `Operation` / `AsyncOperation`           | Creating a UUID-only handle starts nothing. Session submission creates the VM. `run` starts a subprocess inside that VM. | The server produces an image when a non-disposable operation completes. History commit is a separate session action.    | Subprocesses share this VM until operation shutdown. One reader distributes events.                | The handle owner exits its context or calls `shutdown`. The client remains caller-owned.                                                   |
| `LazySession` / `AsyncLazySession`       | The first command starts a VM. Commands reuse it until snapshot; the next command starts from the saved image.           | Snapshot drains commands, stops the VM, and commits one history entry. Command completion alone does not save an image. | Processes survive between commands in the same VM. They do not survive snapshot and restart.       | The wrapper context or `close` saves and stops; `abort` discards unsaved work. The wrapped session and its components remain caller-owned. |

The default commit policy accepts API success even when a process returns a
nonzero exit code. Disposable requests do not advance history. See
{doc}`running-commands`, {doc}`operation`, and {doc}`lazy-session` for complete
examples and failure behavior.

`SyncExecutor` and `AsyncExecutor` are interfaces for command execution and file
reading. They do not add a VM or a lifecycle. Matching that interface does not
mean that two implementations support the same request options.

## Supporting components

| Component         | Responsibility                                                                                  | Does not own                                                 |
| ----------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `contree-client`  | HTTP transport, credentials, API models, image lookup, and remote API calls.                    | SDK history and commit policy.                               |
| Session           | Current image, request policy, branches, and history commits.                                   | The lifetime of a supplied client, store, or file transfer.  |
| Store             | History records, branch pointers, metadata, staged files, and registered background operations. | The remote filesystem images referenced by those records.    |
| FileTransfer      | Prepare uploads and read/download files from a saved image.                                     | A running VM's unsaved filesystem.                           |
| Cache             | Reusable metadata such as upload identifiers and build information.                             | Durable session history. Deleting a cache is not a rollback. |
| Docker builder    | Interpret supported Dockerfile instructions through sessions, file transfer, and cache.         | The lifetime of caller-supplied components.                  |
| Framework adapter | Translate framework calls into executor requests and results.                                   | Its supplied executor or an independent execution engine.    |

SQLite persists local records across Python restarts; ConTree stores the images.
Both are needed to resume a saved session. In-memory stores retain records only
within that store instance. See {doc}`sessions` and {doc}`detached-operations`.

## Backend compatibility for agent adapters

The sandbox adapter sets `disposable=False` for commands and uploads. Its
`upload_files` method submits startup attachments in `RunRequest.files`. Its
`download_files` method calls the executor's `read_file`.

| Backend         | Execute a shell command                                      | Upload after construction                                                                                 | Download                                                                                                    | Save boundary                                                |
| --------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Session         | Yes; a new operation per call.                               | Yes; attachments enter a new operation.                                                                   | Reads the current saved image.                                                                              | Successful non-disposable operation.                         |
| LazySession     | Yes; a subprocess in the current VM.                         | Not through the adapter: command-time `files` raises `ValueError`. Configure files at VM startup instead. | Reads the saved image only while idle with no VM. Active work raises `RuntimeError`; call `snapshot` first. | Explicit snapshot, snapshot policy, or graceful close.       |
| Custom executor | Must implement shell commands and retain filesystem changes. | Must support `RunRequest.files` to support adapter uploads.                                               | Must return the filesystem state promised by the application.                                               | Defined by the implementation and documented to its callers. |

Use Session for an agent that needs unrestricted upload/download tool calls.
Do not assume that wrapping LazySession enables live file transfer. The adapter
serializes its own mutations; other callers sharing an executor must coordinate
their changes. See {doc}`../integrations/langchain` for framework requirements.

## Choose an extension point

For a command default, override `prepare_request`. To instrument operation
lifecycle, override `create_operation`. These hooks retain the existing session
orchestration. See {doc}`customization` for executable examples.

Replacing Store is a larger change. It requires atomic branch comparisons,
consistent history snapshots, staging rules, and atomic detached-operation
completion. A cache replacement has different responsibilities and cannot serve
as a Store. Implement the relevant public contract and test its concurrency and
failure behavior before connecting it to a session.
