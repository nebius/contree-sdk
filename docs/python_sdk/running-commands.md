---
icon: terminal
---

# Run commands and handle results

Use `run()` for a command whose final output you need. The sync call returns a
result directly; the async call must be awaited. For live output, use {doc}`operation`.
All examples below use the variables from {doc}`getting-started`.

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

## Pass an executable and separate arguments

An argument containing spaces remains one argument. The shell does not expand it.
This example prints `a value with spaces` and `exit: 0`.

::::{tab} Sync

<!--
name: test_commands; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="a value with spaces\n")
```
-->

```python
import os
from contree_client.models import StreamRepr, InstanceResultState

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    result = session.run("echo", args=["a value with spaces"], timeout=30)
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
    if isinstance(result.state, InstanceResultState):
        print("exit:", result.state.exit_code)
```

<!--
name: test_commands
```python
call = doc_api.sync.calls_for("spawn_instance")[0]
assert call.kwargs["args"] == ["a value with spaces"]
assert call.kwargs["shell"] is False
assert call.kwargs["timeout"] == 30
assert capsys.readouterr().out == "a value with spaces\nexit: 0\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_commands_async; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="a value with spaces\n")
```
-->

```python
import os
from contree_client.models import StreamRepr, InstanceResultState

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    result = await session.run("echo", args=["a value with spaces"], timeout=30)
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
    if isinstance(result.state, InstanceResultState):
        print("exit:", result.state.exit_code)
```

<!--
name: test_commands_async
```python
call = doc_api.async_client.calls_for("spawn_instance")[0]
assert call.kwargs["args"] == ["a value with spaces"]
assert call.kwargs["shell"] is False
assert call.kwargs["timeout"] == 30
assert capsys.readouterr().out == "a value with spaces\nexit: 0\n"
```
-->

::::

Use `shell="command | another-command > output"` when you need pipes, redirection,
or shell variable expansion. Supply exactly one of `command` and `shell`.
Arguments in `args` are for direct execution; the server ignores them in shell mode.

## Send input without creating a file

`stdin` accepts text, bytes, a local `Path`, or a readable stream. A string is input
text here; it is not a filename. The SDK sends the input and closes remote stdin.
Caller-owned streams remain open.

::::{tab} Sync

<!--
name: test_stdin; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="input from Python\n")
```
-->

```python
import os
from contree_client.models import StreamRepr

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    result = session.run("cat", stdin=b"input from Python\n")
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
```

<!--
name: test_stdin
```python
payload = doc_api.sync.calls_for("spawn_instance")[0].kwargs["stdin"]
assert StreamRepr(value=payload.value, encoding=payload.encoding).as_bytes() == b"input from Python\n"
assert payload.close is True
assert capsys.readouterr().out == "input from Python\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_stdin_async; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="input from Python\n")
```
-->

```python
import os
from contree_client.models import StreamRepr

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    result = await session.run("cat", stdin=b"input from Python\n")
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
```

<!--
name: test_stdin_async
```python
payload = doc_api.async_client.calls_for("spawn_instance")[0].kwargs["stdin"]
assert StreamRepr(value=payload.value, encoding=payload.encoding).as_bytes() == b"input from Python\n"
assert payload.close is True
assert capsys.readouterr().out == "input from Python\n"
```
-->

::::

Use {doc}`files` when the command needs named files instead of stdin.

## Set defaults for later commands

`set_cwd()` and `set_env()` update session defaults and store them with the session.
The remote directory must already exist; `set_cwd()` does not create it.

::::{tab} Sync

<!--
name: test_defaults; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="test\n")
```
-->

```python
import os
from contree_client.models import StreamRepr

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    session.set_cwd("/tmp")
    session.set_env({"APP_MODE": "default", "RETAINED": "yes"})
    result = session.run(shell='printf "%s\\n" "$APP_MODE"', env={"APP_MODE": "test"})
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
```

<!--
name: test_defaults
```python
call = doc_api.sync.calls_for("spawn_instance")[0]
assert call.kwargs["cwd"] == "/tmp"
assert call.kwargs["env"] == {"APP_MODE": "test", "RETAINED": "yes"}
assert capsys.readouterr().out == "test\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_defaults_async; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="test\n")
```
-->

```python
import os
from contree_client.models import StreamRepr

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    await session.set_cwd("/tmp")
    await session.set_env({"APP_MODE": "default", "RETAINED": "yes"})
    result = await session.run(shell='printf "%s\\n" "$APP_MODE"', env={"APP_MODE": "test"})
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
```

<!--
name: test_defaults_async
```python
call = doc_api.async_client.calls_for("spawn_instance")[0]
assert call.kwargs["cwd"] == "/tmp"
assert call.kwargs["env"] == {"APP_MODE": "test", "RETAINED": "yes"}
assert capsys.readouterr().out == "test\n"
```
-->

::::

A per-command `env=` overlays the session's default mapping for that request.
Command values win on duplicate keys. An empty mapping keeps the session defaults;
it does not clear them. Neither the supplied mapping nor the session defaults are
mutated. Override `prepare_environment()` to use another merge policy.
`set_env({"KEY": None})` removes a session default.

Session defaults belong to the session, not a history entry. Rolling back an image
does not roll back these defaults. Constructor `env=` and `cwd=` override loaded
values for that session object; use the setters to persist defaults in the store.

`preserve_env=True` with `disposable=False` asks the server to store environment
values in the result image. Later shell commands inherit image environment values;
direct commands require explicit `env`. This differs from session defaults, which
the SDK sends with each request. An empty string removes a preserved image variable.

## Handle a failed command

A nonzero process exit code is a normal `InstanceResult`. Check it before the next
workflow step. With `disposable=False`, even a nonzero exit can advance history.
`FailedOperationError` means the operation failed or has no usable result.
Cancellation raises `InterruptedError`. See {doc}`troubleshooting` for tested handling.

`stdout`, `stderr`, `state`, and nested fields can be `Ellipsis` when absent.
Use `isinstance` before accessing optional model fields, as in the examples above.
Decode streams with `as_text()` or `as_bytes()`; their raw `value` may be base64.

## Limit execution and output

| Option                     | Meaning                                                                                   |
| -------------------------- | ----------------------------------------------------------------------------------------- |
| `timeout=30`               | Send a 30-second operation limit and use it when waiting. A `timedelta` is also accepted. |
| `truncate_output_at=65536` | Limit captured output in bytes; inspect each stream's `truncated` field.                  |
| `disposable=False`         | Keep the result image and advance history.                                                |
| `hostname="build"`         | Set the instance hostname.                                                                |
| `branch="new-experiment"`  | Save the result on a new branch and select it; see {doc}`branching`.                      |

The client's HTTP timeout is a separate transport setting. If waiting raises or
is cancelled, the SDK attempts to cancel the remote operation and preserves the
original exception. See {doc}`reference/session` for full signatures.
