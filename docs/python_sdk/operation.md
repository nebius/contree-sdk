---
icon: diagram-project
---

# Spawning Subprocesses

A running operation isn't limited to the single process `.run()`/`.spawn()` started. While it's still executing, you can spawn additional processes — subspawns — inside the *same* sandbox and track each one independently. This is useful for a long-lived main process (a server, or a `sleep` placeholder) that you want to poke at with ad-hoc commands without paying for a whole new instance.

## Entering Rich Mode

`.spawn()` on its own only gives you *simple mode*: control over the operation as a whole (see [Simple Mode](#simple-mode) below), with no way to track a second process. Spawning subprocesses requires *rich mode*, entered with `with`/`async with`, which starts a background task (async) or thread (sync) that consumes the operation's live event stream:

````{tab} Async
```python
async with session.run(shell="sleep 300") as operation:
    ...
```

Exiting the block signals the operation (`SIGTERM`), waits for it to stop, and force-cancels it if it doesn't — see {meth}`~contree_sdk.session.AsyncOperation.shutdown`.
````

````{tab} Sync
```python
operation = session.spawn(shell="sleep 300")
with operation:
    ...
```
````

## Spawning and Waiting

Inside the block, `operation.run()` spawns an additional process in the same sandbox and returns a handle that is both waitable (its final result) and iterable (its live events):

````{tab} Async
```{literalinclude} ../../examples/operation/spawn_subprocess.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.AsyncOperation.run` and {meth}`~contree_sdk.session.AsyncSubprocessHandle.wait`.
````

````{tab} Sync
```{literalinclude} ../../examples/operation/spawn_subprocess_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.Operation.run` and {meth}`~contree_sdk.session.SubprocessHandle.wait`.
````

## Streaming Live Output

Instead of waiting for the final result, iterate the handle directly, or pipe it straight to a stream with `pipe_to()`:

````{tab} Async
```python
subprocess = await operation.run("tail -f /var/log/app.log")
async for event in subprocess:
    if event.type in ("stdout", "stderr"):
        print(event.data.value, end="")
```
````

````{tab} Sync
```python
subprocess = operation.run("tail -f /var/log/app.log")
for event in subprocess:
    if event.type in ("stdout", "stderr"):
        print(event.data.value, end="")
```
````

`pipe_to()` decodes each chunk and writes it to the text-or-binary stream you pass, then returns the final result once the subprocess exits:

```python
result = subprocess.pipe_to(stdout=sys.stdout, stderr=sys.stderr)
```

See {meth}`~contree_sdk.session.SubprocessHandle.pipe_to`.

## Signaling and Sending Input

Send stdin or a signal to a specific subprocess through the `Operation`, not the subprocess handle — these calls are addressed by `spid`, which every handle exposes:

````{tab} Async
```python
await operation.send_stdin("more input\n", spid=subprocess.spid)
await operation.signal("SIGINT", spid=subprocess.spid)
```
````

````{tab} Sync
```python
operation.send_stdin("more input\n", spid=subprocess.spid)
operation.signal("SIGINT", spid=subprocess.spid)
```
````

Omit `spid` to address the operation's own main process (`spid=1`) instead.

## Simple Mode

Outside a `with`/`async with` block, `Operation`/`AsyncOperation` still cover the whole operation's own lifecycle — `events()`, `status()`, `send_stdin()`, `signal()`, `cancel()`, `wait()` — as thin, stateless forwards to the client, keyed by the operation's UUID. This is what `session.spawn()` returns when you don't need subspawns, and it's also all you need to reattach to an operation from a different process — since every call is stateless per UUID, reattaching is just constructing a new handle with the same UUID:

````{tab} Async
```python
operation = await session.spawn(shell="./long-task.sh")
result = await operation.wait()

# from anywhere, given the UUID:
from contree_sdk.session import AsyncOperation
reattached = AsyncOperation(client, operation.uuid)
status = await reattached.status()
```
````

````{tab} Sync
```python
operation = session.spawn(shell="./long-task.sh")
result = operation.wait()

# from anywhere, given the UUID:
from contree_sdk.session import Operation
reattached = Operation(client, operation.uuid)
status = reattached.status()
```
````

## Committing the Main Process

Subspawns are runtime-only — they never factor into the session's history. Only the operation's own main process (`spid=1`) can be committed, exactly like a plain `.run(disposable=False)`:

- `await session.run(..., disposable=False)` commits automatically when awaited, or on a clean `async with` exit — see {doc}`running-commands`.
- With `session.spawn()` directly, call {meth}`~contree_sdk.session.ContreeAsyncSession.commit_result` (or {meth}`~contree_sdk.session.ContreeSession.commit_result` for sync) yourself once you have a result.
