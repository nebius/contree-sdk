# Resume a background operation

Use `spawn_detached()` when a command must continue after the current Python
process exits. The session records its UUID, source image, parent entry, branch,
command options, and uploaded attachment metadata. It does not start an event
reader. The server still applies the operation's configured timeout.

Use a SQLite store for persistence across processes. Memory stores implement the
same API but retain records only while that store instance exists. Keep the same
session ID, database, and endpoint when resuming.

## Synchronous execution

The first block submits work and closes the local store and client. It leaves the
remote operation running. Store the operation UUID in your application or retrieve
it through `session.list_operations()` after restarting Python.

<!--
name: test_detached_sync; fixtures: doc_api
```python
doc_api.complete(stdout="saved\n")
```
-->

```python
import os
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession
from contree_sdk.store import SyncSQLiteStore

with (
    ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client,
    SyncSQLiteStore("session.db") as store,
):
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"], session_id="background", store=store)
    record = session.spawn_detached(shell="printf saved > /result.txt; cat /result.txt", disposable=False)
    operation_uuid = record.uuid
```

Run the next block in the process that collects the result. `wait_operation()`
uses the session's commit policy and records completion atomically with history.
It returns the process result, including a nonzero exit code. The consumer needs
the same working directory and connection variables. It obtains the UUID from
the store, so no Python variables from the submitting process are needed. This
example has exactly one pending operation; applications with several operations
must select the intended record or accept a UUID as an argument.

<!-- name: test_detached_sync -->

```python
import os
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession
from contree_sdk.store import SyncSQLiteStore

with (
    ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client,
    SyncSQLiteStore("session.db") as store,
):
    session = ContreeSession(client, session_id="background", store=store)
    pending = session.list_operations()
    (record,) = pending
    operation_uuid = record.uuid
    result = session.wait_operation(operation_uuid)
    repeated_result = session.wait_operation(operation_uuid)
    assert result == repeated_result
    assert session.list_operations() == ()
    assert len(session.history()[0]) == 2
    assert session.list_operations(pending_only=False)[0].history_id is not None
```

<!--
name: test_detached_sync
```python
assert len(doc_api.sync.calls_for("spawn_instance")) == 1
assert len(doc_api.sync.calls_for("follow_operation_events")) == 1
```
-->

## Asynchronous execution

`ContreeAsyncSession` uses native async transport and storage. No event loop or
background reader must remain running between these blocks.

<!--
name: async test_detached_async; fixtures: doc_api
```python
doc_api.complete(stdout="saved\n")
```
-->

```python
import os
from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession
from contree_sdk.store import AsyncSQLiteStore

async with (
    ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client,
    AsyncSQLiteStore("async.db") as store,
):
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"], session_id="background", store=store)
    record = await session.spawn_detached(shell="printf saved > /result.txt; cat /result.txt", disposable=False)
    operation_uuid = record.uuid
```

<!-- name: test_detached_async -->

```python
import os
from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession
from contree_sdk.store import AsyncSQLiteStore

async with (
    ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client,
    AsyncSQLiteStore("async.db") as store,
):
    session = ContreeAsyncSession(client, session_id="background", store=store)
    (record,) = await session.list_operations()
    operation_uuid = record.uuid
    result = await session.wait_operation(operation_uuid)
    repeated_result = await session.wait_operation(operation_uuid)
    assert result == repeated_result
    assert await session.list_operations() == ()
    assert len((await session.history())[0]) == 2
```

<!--
name: test_detached_async
```python
assert len(doc_api.async_client.calls_for("spawn_instance")) == 1
assert len(doc_api.async_client.calls_for("follow_operation_events")) == 1
```
-->

## Branches and commit policy

Completion targets the branch recorded at spawn time. Switching to another branch
during execution does not redirect the result. Completion also does not switch
the active branch. If its original tip changed, completion raises
`SessionConflictError` and leaves the operation pending.

Retry `wait_operation(uuid, branch="recovered")` to retain the result on a new
branch. That branch must not exist. The result still descends from the original
parent entry. An explicit retry does not rerun the remote command.

The default `ApiSuccessCommitPolicy` retains every successful non-disposable
result, including nonzero exit codes. Pass `commit_policy=ZeroExitCommitPolicy()`
when resuming to retain only exit code zero. See {doc}`customization` for custom
policies. Concurrent completion calls share the first stored decision. A later
policy change, branch override, or rollback cannot cause a second commit.

Disposable and policy-rejected results remain readable without a history entry.
Final API failures and cancellation remain readable as the same exceptions.
Completed `wait_operation()` calls use the stored response without remote I/O.
Transport errors remain pending. A timeout or cancellation of a live wait follows
`Operation.wait()` semantics and requests remote cancellation; it does not merely
stop observing the operation.

`wait_operation()` closes its internal handle before returning or raising. Async
cleanup completes even after repeated caller cancellation. Synchronous cleanup
uses a bounded reader join; a blocked transport can keep its reader thread alive
until the stream releases it. See {doc}`operation` for lifecycle details.

## Control and inspect registered work

`detach(operation)` registers an existing session operation without closing its
handle. `restore_operation(uuid)` reconstructs a handle through `create_operation()`
with the original context. Override `create_operation_record()` and
`restore_operation_context()` together to persist application-specific request
fields. Both restoration and commit policies use these hooks. Use that handle to send signals, cancel the operation,
or read events. After `wait()`, `commit_result()` on a restored handle uses the
same atomic completion path. Use `wait_operation()` to replay a stored response.

`list_operations()` returns pending records. Set `pending_only=False` to include
completed records. `OperationRecord.history_id` identifies a retained result;
`response_json` stores the final API response. Records include the effective
command environment and output, but not client credentials. A different client
endpoint is rejected before the UUID is used.

Local file and stdin sources are not serialized or reopened. Attachments retain
their uploaded UUIDs and destination permissions. Restored `OperationContext`
values have `request.files=None` and `request.stdin=None`; inspect `attachments`
and `files` for the submitted inputs. Commit policies must use this persisted
context, rather than source objects. Detached titles and file metadata are fixed
at registration; `commit_result()` cannot override them.

## Failure boundaries and custom stores

Remote submission and local registration are separate operations. If registration
raises normally, `spawn_detached()` requests cancellation and preserves the
registration error. A process crash between remote submission and registration
can leave an unregistered remote operation. Registration does not promise exactly
one remote submission. Retrying submission can start another operation.

Within a registered operation, native stores atomically write the final response,
history entry, branch pointer, and applied file paths. SQLite transactions roll
back all these writes on error or cancellation. Two processes completing the same
record receive the same final outcome. Deleting a session removes its registry
records as well as its history; it does not cancel remote operations.

Custom stores implement `register_operation`, `get_operation`, `list_operations`,
and `finish_operation` from `SyncStore` or `AsyncStore`. Completion must be atomic
and idempotent. Do not implement it as an unlocked lookup followed by `append()`.
The base implementations raise `NotImplementedError` instead of providing an
unsafe fallback. See {doc}`reference/store` for the public contracts.
