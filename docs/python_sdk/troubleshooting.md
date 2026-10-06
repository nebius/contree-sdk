---
icon: triangle-exclamation
---

# Handle failures and unexpected state

Start with the symptom. The API client reports transport and server errors;
the SDK reports execution, history, and build errors.

| Symptom                                                      | Check or action                                                                                               |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `KeyError: CONTREE_TOKEN`, `CONTREE_URL`, or `CONTREE_IMAGE` | Set the variables used by the example; see {doc}`getting-started`.                                            |
| Authentication or profile error                              | Check the endpoint/token pair. `from_profile()` loads a saved profile, not arbitrary environment credentials. |
| Unknown image tag                                            | Import the image on the selected endpoint; see {doc}`images`.                                                 |
| A file from the previous command disappeared                 | The previous run needs `disposable=False`.                                                                    |
| Work disappeared after Python restarted                      | Resume the same `session_id` from the same SQLite database.                                                   |
| Async `image_uuid` is `None`                                 | Await `ensure_ready()` or a session operation before reading it.                                              |
| `ValueError` when resuming                                   | The store has no history for that session ID and no base image was supplied.                                  |
| `SessionConflictError`                                       | Another operation advanced the source branch; see recovery below.                                             |
| `NotImplementedError` from async sandbox sync methods        | Use `aexecute`, `aupload_files`, or `adownload_files`.                                                        |

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

## A command returned a nonzero exit code

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
import os
from contree_client.models import InstanceResultState, StreamRepr

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    result = session.run(shell="echo failed >&2; exit 7")
    if isinstance(result.state, InstanceResultState) and result.state.exit_code != 0:
        if isinstance(result.stderr, StreamRepr):
            print(result.stderr.as_text(), end="")
        print("exit:", result.state.exit_code)
```

<!--
name: test_nonzero_exit
```python
assert session.image_uuid == "base-image"
assert capsys.readouterr().out == "failed\nexit: 7\n"
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
import os
from contree_client.models import InstanceResultState, StreamRepr

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    result = await session.run(shell="echo failed >&2; exit 7")
    if isinstance(result.state, InstanceResultState) and result.state.exit_code != 0:
        if isinstance(result.stderr, StreamRepr):
            print(result.stderr.as_text(), end="")
        print("exit:", result.state.exit_code)
```

<!--
name: test_nonzero_exit_async
```python
assert session.image_uuid == "base-image"
assert capsys.readouterr().out == "failed\nexit: 7\n"
```
-->

::::

With `disposable=False`, inspect the exit code before continuing. A saved command
can have changed files even when its process exits nonzero. Roll back explicitly
if those changes should not remain selected.

## A completed result conflicts with newer history

A completed operation retains its origin. Committing it against a branch that has
advanced raises `SessionConflictError`. Do not retry the mutating command blindly.
You can save its completed result on a new branch instead:

::::{tab} Sync

<!--
name: test_history_conflict; fixtures: doc_api, capsys
```python
doc_api.complete(wait_for=2)
doc_api.complete(wait_for=1)
```
-->

```python
import os
from contree_sdk.exceptions import SessionConflictError

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = session.spawn(shell="echo candidate > /value.txt", disposable=False)
    session.run(shell="echo newer > /value.txt", disposable=False)
    operation.wait()
    try:
        session.commit_result(operation)
    except SessionConflictError:
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
import os
from contree_sdk.exceptions import SessionConflictError

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = await session.spawn(shell="echo candidate > /value.txt", disposable=False)
    await session.run(shell="echo newer > /value.txt", disposable=False)
    await operation.wait()
    try:
        await session.commit_result(operation)
    except SessionConflictError:
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

## Catch an operation failure

Keep command exit-code handling separate from operation failure. If the server
cannot complete the operation successfully, the SDK raises `FailedOperationError`.
This example reports the operation UUID without advancing disposable session state.

::::{tab} Sync

<!--
name: test_operation_failure; fixtures: doc_api, capsys
```python
from contree_client.models import OperationStatus

doc_api.complete(status=OperationStatus.FAILED)
```
-->

```python
import os
from contree_sdk.exceptions import FailedOperationError

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
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
import os
from contree_sdk.exceptions import FailedOperationError

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
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
