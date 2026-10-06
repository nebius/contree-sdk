# Standalone examples

Each program has a synchronous version in `sync/` and an asynchronous version in
`async/`. Short API recipes live in the [documentation](../docs/index.md).

| Program          | Scenario                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| `workflow.py`    | Upload data, save results, compare branches, and reopen SQLite history. |
| `build_image.py` | Create a local build context, build and tag an image, then run it.      |
| `subprocess.py`  | Run two subprocesses within one operation.                              |
| `list_images.py` | List images with limits, tags, and a creation-time filter.              |

## Run a program

Install the checkout and configure a ConTree endpoint. `CONTREE_IMAGE` must name an
image on that endpoint with a POSIX shell and standard utilities, such as BusyBox.

```bash
uv sync --extra async
export CONTREE_URL="https://your-contree-endpoint"
export CONTREE_TOKEN="your-token"
export CONTREE_IMAGE="tag:your-base-image"
uv run python examples/sync/workflow.py
uv run python examples/async/workflow.py
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
