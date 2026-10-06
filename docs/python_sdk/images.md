---
icon: layer-group
---

# Import a Docker image

Use `sync_import_image` or `async_import_image` to import a registry image.
Each helper waits for completion and returns an image UUID for the sandbox factory.

An imported image can be the common starting point for several experiments.
{doc}`Work with a Session <session-model>` explains how to save changes, branch
from a checkpoint, and return to an earlier state.

Configure the endpoint, token, and AI project as described in
{ref}`sandbox-connection`. The registry must be reachable from the ConTree server.
The example imports Alpine through a Docker Hub mirror and assigns the ConTree
tag `alpine:latest`. Replace the registry URL with one available to your server.

## Import and run a command

Save either program as `import_image.py` and run it with Python. Both programs
wait for the import to finish, open a sandbox, and print `Hello from an imported image!`.
The helpers use the same connection configuration as the sandbox factory.

::::{tab} Sync

<!--
name: test_import_image; fixtures: sandbox_api, capsys
```python
from tests.unit.session.factories import operation_response

sandbox_api.command("Hello from an imported image!\n")
for client in (sandbox_api.sync, sandbox_api.async_client):
    client.mock("import_image", "operation-1")
    client.mock("wait_operation", operation_response(result_image_uuid="image-1"))
    client.mocks["resolve_image"].clear()
    client.mock("resolve_image", "image-1")
```
-->

```python
"""Import a registry image and run a command in a sandbox."""

from contree_sdk import create_sandbox_session, sync_import_image


def main() -> None:
    image = sync_import_image("docker://mirror.gcr.io/library/alpine:latest", tag="alpine:latest")
    with create_sandbox_session(image=image) as sandbox:
        result = sandbox.run("echo", args=["Hello from an imported image!"])
        print(result.stdout.as_text(), end="")


main()
```

<!--
name: test_import_image
```python
client = sandbox_api.sync
assert client.calls_for("import_image")[0].kwargs["tag"] == "alpine:latest"
assert client.calls_for("wait_operation")[0].args == ("operation-1",)
assert client.calls_for("spawn_instance")[0].args[1] == "image-1"
assert client.calls_for("operation_subprocess_create")[0].kwargs["args"] == ["Hello from an imported image!"]
assert capsys.readouterr().out == "Hello from an imported image!\n"
```
-->

::::

::::{tab} Async

<!--
name: test_import_image_async; fixtures: sandbox_api, capsys
```python
from tests.unit.session.factories import operation_response

sandbox_api.command("Hello from an imported image!\n")
for client in (sandbox_api.sync, sandbox_api.async_client):
    client.mock("import_image", "operation-1")
    client.mock("wait_operation", operation_response(result_image_uuid="image-1"))
    client.mocks["resolve_image"].clear()
    client.mock("resolve_image", "image-1")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session, async_import_image


async def main() -> None:
    image = await async_import_image("docker://mirror.gcr.io/library/alpine:latest", tag="alpine:latest")
    async with create_sandbox_session(image=image) as sandbox:
        result = await sandbox.run("echo", args=["Hello from an imported image!"])
        print(result.stdout.as_text(), end="")


asyncio.run(main())
```

<!--
name: test_import_image_async
```python
client = sandbox_api.async_client
assert client.calls_for("import_image")[0].kwargs["tag"] == "alpine:latest"
assert client.calls_for("wait_operation")[0].args == ("operation-1",)
assert client.calls_for("spawn_instance")[0].args[1] == "image-1"
assert client.calls_for("operation_subprocess_create")[0].kwargs["args"] == ["Hello from an imported image!"]
assert capsys.readouterr().out == "Hello from an imported image!\n"
```
-->

::::

The helpers return only after a successful import. A failed import raises
`FailedOperationError`. Assigning an existing ConTree tag moves it to the imported image.

The import supplies a filesystem. It does not start the registry image's `CMD`
or `ENTRYPOINT`, and it does not apply its `WORKDIR`. Select the command and
working directory when running the sandbox.

## Reuse the imported image

| Reference                                      | Use                                                            |
| ---------------------------------------------- | -------------------------------------------------------------- |
| `docker://mirror.gcr.io/library/alpine:latest` | Registry source passed to an import helper.                    |
| `tag:alpine:latest`                            | ConTree tag passed to the sandbox factory.                     |
| The returned image UUID                        | The specific imported filesystem, even if its tag later moves. |

Registry sources such as `docker://mirror.gcr.io/library/alpine:latest` belong in
an import helper. They cannot be used as ConTree image references in
`create_sandbox_session(image=...)`. Pass the returned UUID or a ConTree tag instead.
The factory does not import missing images; an unknown tag raises `NotFoundError`.

Dockerfile `FROM` has separate behavior: the builder imports a missing base image
from its registry. See {doc}`building-images`.

## Configuration

The import cache maps a registry source to its imported ConTree image UUID.
A repeated call with the same source, requested ConTree tag, and credentials
returns that UUID without another registry import. If `tag=` is supplied, the
helper reapplies it to the cached image. The image itself stays on the ConTree
server; the local cache contains only its UUID.

Records expire after one hour by default. Until then, a moved registry tag still
returns the cached image. Pass `no_cache=True` to import it again and refresh the
record. Keep cached images available on the server.

Records are stored in `$XDG_CACHE_HOME/contree/images.sqlite3`, or
`~/.cache/contree/images.sqlite3` when XDG is unset. Connections and registry
credentials have separate cache keys. Credentials are hashed, not stored in plaintext.
Use `cache_ttl=` to change the lifetime or `cache_dir=` to choose another directory.

For several operations, initialize a client once and pass it through `client=`.
The client is a shared dependency for import, build, and sandbox operations.
See the complete Sync/Async example in {ref}`shared-image-client`.
The caller closes a supplied client. Helpers close clients they create themselves.

Pass an `ImageImportRegistry` object instead of a string when the registry needs
credentials. Pass `store=` to use your own Store for import results.
See {doc}`reference/images` for connection and retention parameters.

Continue with {doc}`building-images` to build a Docker image from a Dockerfile.
