# Standalone examples

Each program has a synchronous version in `sync/` and an asynchronous version in
`async/`. Short API recipes live in the [documentation](../docs/index.md).

| Program          | Scenario                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| `sandbox.py`     | Create a configured sandbox and run commands with automatic cleanup.    |
| `workflow.py`    | Upload data, save results, compare branches, and reopen SQLite history. |
| `build_image.py` | Create a local build context, build and tag an image, then run it.      |
| `subprocess.py`  | Run two subprocesses within one operation.                              |
| `list_images.py` | List images with limits, tags, and a creation-time filter.              |

## Run a program

Configure the endpoint, token, and AI project using the
[connection guide](../docs/python_sdk/getting-started.md#connection-sources).
The sandbox examples use `image="tag:alpine:latest"`. Replace this tag with an
image available on your endpoint.

```bash
uv sync --extra async
uv run python examples/sync/sandbox.py
uv run python examples/async/sandbox.py
```

`workflow.py` creates `workflow.db` in the current directory and retains its server
images. Each run uses a new session ID. `build_image.py` assigns or moves the tag
`example/greeter:latest` on the selected server.

## Test all examples

Each Python script contains its own `test_...` function. Tests run the script with
`contree_client.testing`, real SDK logic, and temporary local storage. They check
requests and results without a server or credentials.

```bash
uv sync --extra dev
uv run pytest examples
uv run pytest
```

The default pytest run includes both these scripts and Markdown scenarios. Adding
a Python example without a test fails collection.
