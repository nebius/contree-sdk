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

Use `image="tag:alpine:latest"` with `create_sandbox_session` in later programs,
including {doc}`getting-started`. There is no need to import before every command.

| Reference                                      | Use                                                            |
| ---------------------------------------------- | -------------------------------------------------------------- |
| `docker://mirror.gcr.io/library/alpine:latest` | Registry source passed to an import helper.                    |
| `tag:alpine:latest`                            | ConTree tag passed to the sandbox factory.                     |
| The returned image UUID                        | The specific imported filesystem, even if its tag later moves. |

Registry tags and ConTree tags are separate names. `create_sandbox_session`
resolves the supplied image during context entry; it does not import a missing
image. An unknown tag raises the client's `NotFoundError`.

## Configuration

Import results are cached for one hour in `$XDG_CACHE_HOME/contree/images.sqlite3`,
or `~/.cache/contree/images.sqlite3` when XDG is unset. Connections and registry
credentials have separate cache keys. Credentials are hashed, not stored in plaintext.
Pass `no_cache=True` to import a changed registry tag again and refresh the record.
Use `cache_ttl=` to change the lifetime or `cache_dir=` to choose another directory.
The cache stores references; keep the corresponding server images available.

For several operations, initialize a client once and pass it through `client=`.
The client is a shared dependency for import, build, and sandbox operations.
See the complete Sync/Async example in {ref}`shared-image-client`.
The caller closes a supplied client. Helpers close clients they create themselves.

Pass an `ImageImportRegistry` object instead of a string when the registry needs
credentials. See {doc}`reference/images` for connection and cache parameters.

Continue with {doc}`building-images` to build a Docker image from a Dockerfile.
