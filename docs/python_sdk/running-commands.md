# Running Commands

Contree SDK provides multiple ways to execute commands in containers, from simple shell commands to complex workflows with file handling and custom I/O.

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

See {meth}`ContreeImage.run() <contree_sdk.sdk.objects.image.ContreeImage.run>` and {meth}`ContreeSession.run() <contree_sdk.sdk.objects.session.ContreeSession.run>` for all options.
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`ContreeImageSync.run() <contree_sdk.sdk.objects.image.ContreeImageSync.run>` and {meth}`ContreeSessionSync.run() <contree_sdk.sdk.objects.session.ContreeSessionSync.run>` for all options.
````

## Working with Files

You can upload and use files in your commands by specifying local file paths or pre-uploaded file objects:

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

You can provide files to commands in several ways:

- **Local file paths**: `files=["/path/to/local/file.txt"]` - Upload files directly
- **File mapping**: `files={"dest.txt": "/local/source.txt"}` - Upload with custom names
- **Pre-uploaded files**: `files={"script.sh": uploaded_file_object}` - Use files uploaded via `client.files.upload()`

## Advanced I/O Handling

You can use Python I/O objects for more sophisticated input/output handling:

````{tab} Async
```{literalinclude} ../../examples/run/run_io_objects.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImage.run` for I/O parameter details.
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_io_objects_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImageSync.run` for I/O parameter details.
````

### Supported I/O Types

- **StringIO**: For text-based input/output
- **BytesIO**: For binary data handling
- **File objects**: Use `open()` file handles directly
- **PIPE**: Capture stderr/stdout as byte streams
- **bytes type**: Get output as bytes instead of strings

## Subprocess-like Interface (Sync Only)

You can use a subprocess-like interface for more control over process execution:

```{literalinclude} ../../examples/run/run_popen_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {class}`~contree_sdk.sdk.objects.subprocess.ContreeProcessSync` for the full subprocess API.

### Popen Features

- **Process control**: Use `wait()`, `communicate()`, and check `returncode`
- **Environment variables**: Pass custom `env` dictionary
- **Working directory**: Set `cwd` parameter
- **Shell commands**: Enable with `shell=True`
- **Error handling**: Check `returncode` and `stderr` for failures

## Command Parameters

### Core Parameters

- **`shell`**: Execute as shell command (e.g., `"ls -la | grep txt"`)
- **`command`**: Executable path (e.g., `"/bin/ls"`)
- **`args`**: Command arguments as tuple (e.g., `("-la", "/tmp")`)
- **`stdin`**: Input data (string, bytes, or I/O object)
- **`env`**: Environment variables as dictionary

### I/O Parameters

- **`stdout`**: Redirect stdout (StringIO, BytesIO, file path, or `bytes`)
- **`stderr`**: Redirect stderr (StringIO, BytesIO, PIPE, or `bytes`)
- **`files`**: Upload files (list of paths or dict mapping)

### Execution Parameters

- **`cwd`**: Working directory inside container
- **`disposable`**: Whether to persist changes (default: True for runs, False for sessions)

## Result Objects

Command execution returns result objects with:

- **`stdout`**: Command output as string (or specified type)
- **`stderr`**: Error output as string (or specified type)
- **`exit_code`**: Process exit code (0 = success)
- **`uuid`**: UUID of the resulting image state
