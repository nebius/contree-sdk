---
icon: terminal
---

# Running Commands

`ContreeSession`/`ContreeAsyncSession` provide a single `.run()` method covering shell commands, positional commands with arguments, file uploads, and stdin.

## Basic Command Execution

You can run commands using shell syntax or by specifying command and arguments separately:

````{tab} Async
```{literalinclude} ../../examples/run/run_simple.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.ContreeAsyncSession.run` for all options.
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.ContreeSession.run` for all options.
````

## Command Execution Mode

You can execute commands by specifying the executable path and arguments separately:

````{tab} Async
```{literalinclude} ../../examples/run/run_command.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_command_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

### Command vs Shell Mode

- **Command mode**: Use `command="/bin/ls"` with `args=["-la", "/tmp"]` for direct execution without shell interpretation
- **Shell mode**: Use `shell="ls -la /tmp"` for shell commands with pipes, redirects, and wildcards
- **Environment variables**: Pass `env={"VAR": "value"}` to set environment for command execution

### Preserving Environment Variables

By default, values passed through `env` are available only to the current command. Set `preserve_env=True`
with `disposable=False` when those variables should be written into the resulting image and inherited by
later commands on the same session:

````{tab} Async
```python
await session.run(
    shell="true",
    env={"MY_PERSISTED_VAR": "persisted_value"},
    preserve_env=True,
    disposable=False,
)
result = await session.run("/bin/printenv", args=["MY_PERSISTED_VAR"])
```
````

````{tab} Sync
```python
session.run(
    shell="true",
    env={"MY_PERSISTED_VAR": "persisted_value"},
    preserve_env=True,
    disposable=False,
)
result = session.run("/bin/printenv", args=["MY_PERSISTED_VAR"])
```
````

On the ConTree side, `preserve_env=True` merges the image's existing `metadata/env` entries with the `env`
values from the request, with request values taking priority, then writes the merged values back to
`metadata/env` in the resulting image. Setting a variable to an empty string removes it from the preserved
environment.

## Working with Files

Pass files to bake into the resulting image directly through `.run(files=...)` — the SDK deduplicates uploads by content hash under the hood. `files` accepts a list of local paths, a dict mapping a destination path to a local path or raw bytes, or `stdin` for input redirection:

````{tab} Async
```{literalinclude} ../../examples/run/run_files.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_files_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

### File Upload Methods

- **Local file paths**: `files=["/path/to/local/file.txt"]` — uploads under `/<basename>` in the image
- **Destination mapping**: `files={"/dest.txt": "/local/source.txt"}` — upload with a specific destination path
- **Inline content**: `files={"/dest.txt": b"raw bytes"}` — no local file needed

## Command Parameters

### Core Parameters

- **`shell`**: Execute as shell command (e.g., `"ls -la | grep txt"`)
- **`command`**: Executable path (e.g., `"/bin/ls"`)
- **`args`**: Command arguments (e.g., `["-la", "/tmp"]`)
- **`stdin`**: Input data (string, bytes, or a local file `Path`)
- **`env`**: Environment variables as dictionary
- **`files`**: Files to upload (list of paths or dict mapping — see above)

### Execution Parameters

- **`cwd`**: Working directory inside the container
- **`disposable`**: Whether to persist changes (default: `True` — the session's image and history are unchanged)
- **`preserve_env`**: Whether to persist `env` values into the resulting image environment
- **`branch`**: Branch to advance instead of the active one, for a non-disposable run (see {doc}`branching`)
- **`timeout`**: Maximum time to wait for the operation, in seconds or as a `timedelta`
- **`truncate_output_at`**: Cap on captured stdout/stderr size, in bytes

## Result Objects

`.run()` returns `contree-client`'s `InstanceResult` as-is:

- **`stdout`/`stderr`**: `StreamRepr` objects — decode with `.as_text()` or `.as_bytes()`
- **`state.exit_code`**: process exit code (`0` = success)

For a non-disposable run, the session's `image_uuid` reflects the newly-committed image, and a new entry is appended to the session's history (see {doc}`branching`).
