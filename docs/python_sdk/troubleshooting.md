---
icon: triangle-exclamation
---

# Handle failures and unexpected state

| Symptom                                               | Check or action                                                                                                                                       |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Authentication or profile error                       | Check the URL, token, and AI project; see {ref}`sandbox-connection`.                                                                                  |
| Unknown image tag                                     | Import the image on the selected endpoint; see {doc}`images`.                                                                                         |
| A file from the previous command disappeared          | For explicit `ContreeSession`, check that `disposable=True` was not requested. For a lazy sandbox, check whether an exception discarded unsaved work. |
| Work disappeared after Python restarted               | Resume the same `session_id` from the same SQLite database.                                                                                           |
| Explicit async session has no `image_uuid` yet        | Await `ensure_ready()` or a session operation before reading it.                                                                                      |
| `ValueError` when resuming                            | Supply a base image for a new tree, or `node_id` when existing history has multiple leaves.                                                           |
| A completed result did not become current             | A newer local selection exists; select the saved result explicitly as shown below.                                                                    |
| `NotImplementedError` from async sandbox sync methods | Use `aexecute`, `aupload_files`, or `adownload_files`.                                                                                                |

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

## Fail a sandbox workflow on a nonzero exit

A nonzero command exit returns a result. Calling `run_workflow()` below raises
inside the context, discards unsaved changes, and closes the VM.

::::{tab} Sync

<!--
name: test_sandbox_nonzero; fixtures: sandbox_api
```python
sandbox_api.command(exit_code=7)
import pytest
```
-->

```python
from contree_sdk import create_sandbox_session


def run_workflow() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as sandbox:
        result = sandbox.run(shell="exit 7")
        if result.state.exit_code != 0:
            raise RuntimeError(f"Command failed with exit code {result.state.exit_code}")
```

<!--
name: test_sandbox_nonzero
```python
with pytest.raises(RuntimeError, match="exit code 7"):
    run_workflow()
assert len(sandbox_api.sync.calls_for("cancel_operation")) == 1
assert not sandbox_api.sync.calls_for("get_operation_status")
```
-->

::::

::::{tab} Async

<!--
name: async test_sandbox_nonzero_async; fixtures: sandbox_api
```python
sandbox_api.command(exit_code=7)
import pytest
```
-->

```python
from contree_sdk import create_sandbox_session


async def run_workflow() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as sandbox:
        result = await sandbox.run(shell="exit 7")
        if result.state.exit_code != 0:
            raise RuntimeError(f"Command failed with exit code {result.state.exit_code}")
```

<!--
name: test_sandbox_nonzero_async
```python
with pytest.raises(RuntimeError, match="exit code 7"):
    await run_workflow()
assert len(sandbox_api.async_client.calls_for("cancel_operation")) == 1
assert not sandbox_api.async_client.calls_for("get_operation_status")
```
-->

::::

## Advanced: a command returned a nonzero exit code

This is a process result, so `run()` returns it without raising `FailedOperationError`.
The example uses disposable execution and leaves the session image unchanged.

::::{tab} Sync

<!--
name: test_nonzero_exit; fixtures: doc_api, capsys
```python
doc_api.complete(stderr="failed\n", exit_code=7)
```
-->

```python
from contree_sdk import ContreeSession, create_sandbox_session


with create_sandbox_session(session_type=ContreeSession, image="tag:alpine:latest") as session:
    result = session.run(shell="echo failed >&2; exit 7", disposable=True)
    if result.state.exit_code != 0:
        print(result.stderr)
        print("exit:", result.state.exit_code)
```

<!--
name: test_nonzero_exit
```python
assert session.image_uuid == "base-image"
assert capsys.readouterr().out == "failed\n\nexit: 7\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_nonzero_exit_async; fixtures: doc_api, capsys
```python
doc_api.complete(stderr="failed\n", exit_code=7)
```
-->

```python
from contree_sdk import ContreeAsyncSession, create_sandbox_session


async with create_sandbox_session(session_type=ContreeAsyncSession, image="tag:alpine:latest") as session:
    result = await session.run(shell="echo failed >&2; exit 7", disposable=True)
    if result.state.exit_code != 0:
        print(result.stderr)
        print("exit:", result.state.exit_code)
```

<!--
name: test_nonzero_exit_async
```python
assert session.image_uuid == "base-image"
assert capsys.readouterr().out == "failed\n\nexit: 7\n"
```
-->

::::

Commands save by default. Inspect the exit code before continuing. A saved command
can have changed files even when its process exits nonzero. Roll back explicitly
if those changes should not remain selected.

## Advanced: select a late result

A completed operation retains its original parent. If local navigation or another
operation changes the selected position, committing the result saves a sibling
without selecting it. To save and select that result, give it a local branch name:

::::{tab} Sync

<!--
name: test_history_conflict; fixtures: doc_api, capsys
```python
doc_api.complete(wait_for=2)
doc_api.complete(wait_for=1)
```
-->

```python
from contree_sdk import ContreeSession, create_sandbox_session


with create_sandbox_session(session_type=ContreeSession, image="tag:alpine:latest") as session:
    operation = session.spawn(shell="echo candidate > /value.txt")
    session.run(shell="echo newer > /value.txt")
    operation.wait()
    session.commit_result(operation, branch="recovered", title="Recovered result")
    print(session.image_uuid)
```

<!--
name: test_history_conflict
```python
assert dict(session.list_branches())["recovered"] is True
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_history_conflict_async; fixtures: doc_api, capsys
```python
doc_api.complete(wait_for=2)
doc_api.complete(wait_for=1)
```
-->

```python
from contree_sdk import ContreeAsyncSession, create_sandbox_session


async with create_sandbox_session(session_type=ContreeAsyncSession, image="tag:alpine:latest") as session:
    operation = await session.spawn(shell="echo candidate > /value.txt")
    await session.run(shell="echo newer > /value.txt")
    await operation.wait()
    await session.commit_result(operation, branch="recovered", title="Recovered result")
    print(session.image_uuid)
```

<!--
name: test_history_conflict_async
```python
assert dict(await session.list_branches())["recovered"] is True
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

Choose a fresh recovery branch name. The newer branch remains intact. The recovery
branch selects the completed operation's image; it does not merge the two filesystems.

## Waiting failed, timed out, or was cancelled

`Operation.wait()` attempts cancellation when waiting raises and keeps the original
exception. A cancelled operation raises `InterruptedError`; an operation with no
successful result raises `FailedOperationError`. Client transport errors can also
propagate. Cleanup is best effort: retain the operation UUID if you need to inspect
its server status afterward.

A subprocess wait timeout does not itself terminate the whole operation. Use its
operation's `signal()` or `cancel()`, or leave the operation context to shut it down.
See {doc}`operation` and {doc}`reference/exceptions`.

## Advanced: catch an operation failure

If the server cannot complete the operation, the SDK raises `FailedOperationError`
and leaves history unchanged. Keep the operation UUID to investigate the failure:

::::{tab} Sync

<!--
name: test_operation_failure; fixtures: doc_api, capsys
```python
from contree_client.models import OperationStatus

doc_api.complete(status=OperationStatus.FAILED)
```
-->

```python
from contree_sdk import ContreeSession, create_sandbox_session
from contree_sdk.exceptions import FailedOperationError


with create_sandbox_session(session_type=ContreeSession, image="tag:alpine:latest") as session:
    try:
        session.run("echo", args=["hello"])
    except FailedOperationError as error:
        print("failed operation:", error.operation_uuid)
```

<!--
name: test_operation_failure
```python
assert session.image_uuid == "base-image"
assert capsys.readouterr().out == "failed operation: operation-1\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_operation_failure_async; fixtures: doc_api, capsys
```python
from contree_client.models import OperationStatus

doc_api.complete(status=OperationStatus.FAILED)
```
-->

```python
from contree_sdk import ContreeAsyncSession, create_sandbox_session
from contree_sdk.exceptions import FailedOperationError


async with create_sandbox_session(session_type=ContreeAsyncSession, image="tag:alpine:latest") as session:
    try:
        await session.run("echo", args=["hello"])
    except FailedOperationError as error:
        print("failed operation:", error.operation_uuid)
```

<!--
name: test_operation_failure_async
```python
assert session.image_uuid == "base-image"
assert capsys.readouterr().out == "failed operation: operation-1\n"
```
-->

::::
