---
icon: terminal
---

# Run commands and handle results

Use `run()` for a command whose final output you need. The sync call returns a
result directly; the async call must be awaited. For live output, use {doc}`operation`.
Configure a connection as described in {ref}`sandbox-connection`.

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
name: test_commands; fixtures: sandbox_api, capsys
```python
sandbox_api.command(stdout="a value with spaces\n")
```
-->

```python
from contree_sdk import create_sandbox_session


with create_sandbox_session(image="tag:alpine:latest") as session:
    result = session.run("echo", args=["a value with spaces"], timeout=30)
    print(result.stdout.as_text(), end="")
    print("exit:", result.state.exit_code)
```

<!--
name: test_commands
```python
call = sandbox_api.sync.calls_for("operation_subprocess_create")[0]
assert call.kwargs["args"] == ["a value with spaces"]
assert call.kwargs["shell"] is False
assert capsys.readouterr().out == "a value with spaces\nexit: 0\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_commands_async; fixtures: sandbox_api, capsys
```python
sandbox_api.command(stdout="a value with spaces\n")
```
-->

```python
from contree_sdk import create_sandbox_session


async with create_sandbox_session(image="tag:alpine:latest") as session:
    result = await session.run("echo", args=["a value with spaces"], timeout=30)
    print(result.stdout.as_text(), end="")
    print("exit:", result.state.exit_code)
```

<!--
name: test_commands_async
```python
call = sandbox_api.async_client.calls_for("operation_subprocess_create")[0]
assert call.kwargs["args"] == ["a value with spaces"]
assert call.kwargs["shell"] is False
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
name: test_stdin; fixtures: sandbox_api, capsys
```python
sandbox_api.command(stdout="input from Python\n")
```
-->

```python
from contree_sdk import create_sandbox_session


with create_sandbox_session(image="tag:alpine:latest") as session:
    result = session.run("cat", stdin=b"input from Python\n")
    print(result.stdout.as_text(), end="")
```

<!--
name: test_stdin
```python
from contree_client.models import StreamRepr


payload = sandbox_api.sync.calls_for("operation_subprocess_create")[0].kwargs["stdin"]
assert StreamRepr(value=payload.value, encoding=payload.encoding).as_bytes() == b"input from Python\n"
assert payload.close is True
assert capsys.readouterr().out == "input from Python\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_stdin_async; fixtures: sandbox_api, capsys
```python
sandbox_api.command(stdout="input from Python\n")
```
-->

```python
from contree_sdk import create_sandbox_session


async with create_sandbox_session(image="tag:alpine:latest") as session:
    result = await session.run("cat", stdin=b"input from Python\n")
    print(result.stdout.as_text(), end="")
```

<!--
name: test_stdin_async
```python
from contree_client.models import StreamRepr


payload = sandbox_api.async_client.calls_for("operation_subprocess_create")[0].kwargs["stdin"]
assert StreamRepr(value=payload.value, encoding=payload.encoding).as_bytes() == b"input from Python\n"
assert payload.close is True
assert capsys.readouterr().out == "input from Python\n"
```
-->

::::

Use {doc}`files` when the command needs named files instead of stdin.

## Set defaults for later commands

Pass `cwd` and `env` to the factory to set defaults for its commands.
The remote working directory must already exist.

::::{tab} Sync

<!--
name: test_defaults; fixtures: sandbox_api, capsys
```python
sandbox_api.command(stdout="test\n")
```
-->

```python
from contree_sdk import create_sandbox_session


with create_sandbox_session(
    image="tag:alpine:latest", cwd="/tmp", env={"APP_MODE": "default", "RETAINED": "yes"}
) as session:
    result = session.run(shell='printf "%s\\n" "$APP_MODE"', env={"APP_MODE": "test"})
    print(result.stdout.as_text(), end="")
```

<!--
name: test_defaults
```python
call = sandbox_api.sync.calls_for("operation_subprocess_create")[0]
assert call.kwargs["cwd"] == "/tmp"
assert call.kwargs["env"] == {"APP_MODE": "test", "RETAINED": "yes"}
assert capsys.readouterr().out == "test\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_defaults_async; fixtures: sandbox_api, capsys
```python
sandbox_api.command(stdout="test\n")
```
-->

```python
from contree_sdk import create_sandbox_session


async with create_sandbox_session(
    image="tag:alpine:latest", cwd="/tmp", env={"APP_MODE": "default", "RETAINED": "yes"}
) as session:
    result = await session.run(shell='printf "%s\\n" "$APP_MODE"', env={"APP_MODE": "test"})
    print(result.stdout.as_text(), end="")
```

<!--
name: test_defaults_async
```python
call = sandbox_api.async_client.calls_for("operation_subprocess_create")[0]
assert call.kwargs["cwd"] == "/tmp"
assert call.kwargs["env"] == {"APP_MODE": "test", "RETAINED": "yes"}
assert capsys.readouterr().out == "test\n"
```
-->

::::

A per-command `env=` overlays the session's default mapping for that request.
Command values win on duplicate keys. An empty mapping keeps the session defaults;
it does not clear them. Neither the supplied mapping nor the session defaults are
mutated. Advanced session subclasses can override `prepare_environment()` to
change this policy; see {doc}`customization`.

Session defaults belong to the session, not a history entry. Rolling back an image
does not roll back these defaults. Constructor `env=` and `cwd=` override loaded
values for that session object. Explicit `ContreeSession` implementations provide
`set_cwd()` and `set_env()` for persisted updates.

## Handle a failed command

A nonzero exit code is returned in `result.state.exit_code`. Check it before the
next step. A failed command can still change files; raise an exception inside the
sandbox context to discard changes since the last snapshot. See
{doc}`troubleshooting` for advanced operation failures and history conflicts.

The examples use commands that return stdout and exit status. When inspecting
partial or externally supplied API responses, these fields can be `Ellipsis`.
Check their model types before reading them. Decode streams with `as_text()` or
`as_bytes()`; the raw `value` can be base64.

## Limit execution and output

| Option | Meaning |
| --- | --- |
| `timeout=30` | Limit the command wait to 30 seconds; a timeout attempts to kill that subprocess. |
| `truncate_output_at=65536` | Limit captured output in bytes; inspect the stream's `truncated` field. |
| `cwd="/tmp"` | Set the working directory for this command. |
| `env={"MODE": "test"}` | Override session environment defaults for this command. |

The client's HTTP timeout is a separate transport setting. Normal context exit
saves pending filesystem changes; it does not preserve running processes. See
{doc}`lazy-session` for snapshot policies and cancellation behavior.

## Advanced: use an independent operation per command

Select `session_type=ContreeSession` (or `ContreeAsyncSession` for async code) in
`create_sandbox_session` when each command needs its own VM. With these classes,
commands are disposable by default; use `disposable=False` to save their results.
They also support startup `files`, `hostname`, and `preserve_env` options that the
default lazy session rejects. See {doc}`files`, {doc}`branching`, and
{doc}`manual-sandbox` for explicit control and manual assembly.
