---
icon: file-code
---

# Build a Docker image

Use `sync_build_image` or `async_build_image` when your setup lives in a Dockerfile.
Each helper runs build steps on ConTree and returns an image UUID for a sandbox.
You do not need a local Docker daemon.

## Create a small build context

Configure a connection as described in {ref}`sandbox-connection`. The builder
resolves `alpine:latest` in ConTree, or imports it from Docker Hub if it is missing.
Create `build-context/Dockerfile`:

```dockerfile
FROM alpine:latest
COPY message.txt /message.txt
RUN cat /message.txt > /built.txt
```

Create `build-context/message.txt` with this content and a final newline:

```text
Hello from a built image!
```

## Build and read the result

Run this code from the directory containing `build-context`. Build history and
file uploads are cached on disk by default.

::::{tab} Sync

<!--
name: test_build; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("resolve_image", "image-1")
```
-->

```python
"""Build an image and read its output in a sandbox."""

from contree_sdk import create_sandbox_session, sync_build_image


def main() -> None:
    image = sync_build_image("build-context")
    with create_sandbox_session(image=image) as sandbox:
        content = sandbox.read_file("/built.txt")
        print(content.decode(), end="")


main()
```

<!--
name: test_build
```python
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["disposable"] is False
from pathlib import Path


source_file = doc_api.sync.calls_for("ensure_file")[0].args[0]
assert source_file.closed
assert not Path(source_file.name).exists()
assert doc_api.sync.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::
::::{tab} Async

<!--
name: test_build_async; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("resolve_image", "image-1")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session, async_build_image


async def main() -> None:
    image = await async_build_image("build-context")
    async with create_sandbox_session(image=image) as sandbox:
        content = await sandbox.read_file("/built.txt")
        print(content.decode(), end="")


asyncio.run(main())
```

<!--
name: test_build_async
```python
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert doc_api.async_client.calls_for("ensure_file")[0].args[0].closed
assert doc_api.async_client.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::

The output is `Hello from a built image!`. Changing `message.txt` changes the input
hash and invalidates the dependent layer. The build result is a ConTree filesystem
image. Dockerfile support is a subset listed below; this does not create a local
Docker image.

## Supported Dockerfile behavior

`FROM`, `RUN`, `COPY`, `ADD`, `WORKDIR`, `ENV`, `ARG`, and `USER` are implemented.
The builder supports multiple stages, `COPY --from`, `.dockerignore`, and build
arguments. It interprets a subset of Dockerfile syntax, not the complete Docker build specification.

`CMD`, `ENTRYPOINT`, `LABEL`, `EXPOSE`, `VOLUME`, `STOPSIGNAL`, `MAINTAINER`,
`HEALTHCHECK`, `ONBUILD`, and `SHELL` are accepted but have no effect.
Unknown instructions raise `ValueError`. A nonzero `RUN` exit raises `DockerBuildError`.

The output is a filesystem image. Startup instructions and Docker configuration
are not reproduced. `ENV`, `WORKDIR`, and `USER` guide build steps; pass the desired
runtime environment and working directory when executing the resulting image.
`WORKDIR` sets a command's directory; ensure the directory exists in the image.

## Configuration

### Persistent cache


| Component | What it records                                           |
| --------- | --------------------------------------------------------- |
| `storage=` | History and branch pointers used to reuse built layers.   |
| `cache=`  | Uploaded-file and URL-download metadata used by COPY/ADD. |

The helpers use SQLite by default in `$XDG_CACHE_HOME/contree/`, with
`~/.cache/contree/` as the fallback. Build history is stored in `builds.sqlite3`;
upload metadata is stored in `images.sqlite3`. Set `cache_dir=` to change the directory.
Keep referenced images and uploaded files
available on the server. `no_cache=True` disables layer reuse; it does not force
identical file content to be uploaded again.

The default build session ID derives from the context path and connection scope. Supply `session_id=`
when you need a stable identity after moving a context. Avoid concurrent builds
that mutate the same build session.

(shared-image-client)=
### Share one client

For a workflow with several operations, initialize a client once. Pass it through
`client=` as a dependency to the import helper, build helper, and sandbox factory.
This reuses the connection and gives your application one place to configure it.
Each operation leaves this client open; the outer context closes it.

The following programs import the base under the `alpine:latest` ConTree tag,
build the context above, and read its result. The Dockerfile's `FROM alpine:latest`
then resolves that imported image.

::::{tab} Sync

<!--
name: test_shared_client_sync; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("import_image", "operation-1")
    client.mock("resolve_image", "image-1")
```
-->

```python
"""Reuse one client for import, build, and sandbox operations."""

from contree_client import profiles
from contree_client.sync import ContreeClient

from contree_sdk import create_sandbox_session, sync_build_image, sync_import_image


def main() -> None:
    profile = profiles.from_env() or profiles.resolve_profile()
    with ContreeClient.from_profile(profile) as client:
        sync_import_image(
            "docker://mirror.gcr.io/library/alpine:latest",
            tag="alpine:latest",
            client=client,
        )
        image = sync_build_image("build-context", client=client)
        with create_sandbox_session(image=image, client=client) as sandbox:
            content = sandbox.read_file("/built.txt")
            print(content.decode(), end="")


main()
```

<!--
name: test_shared_client_sync
```python
assert len(doc_api.sync.calls_for("import_image")) == 1
assert len(doc_api.sync.calls_for("spawn_instance")) == 1
assert doc_api.sync.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::

::::{tab} Async

<!--
name: test_shared_client_async; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("import_image", "operation-1")
    client.mock("resolve_image", "image-1")
```
-->

```python
import asyncio

from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import create_sandbox_session, async_build_image, async_import_image


async def main() -> None:
    profile = profiles.from_env() or profiles.resolve_profile()
    async with ContreeAsyncClient.from_profile(profile) as client:
        await async_import_image(
            "docker://mirror.gcr.io/library/alpine:latest",
            tag="alpine:latest",
            client=client,
        )
        image = await async_build_image("build-context", client=client)
        async with create_sandbox_session(image=image, client=client) as sandbox:
            content = await sandbox.read_file("/built.txt")
            print(content.decode(), end="")


asyncio.run(main())
```

<!--
name: test_shared_client_async
```python
assert len(doc_api.async_client.calls_for("import_image")) == 1
assert len(doc_api.async_client.calls_for("spawn_instance")) == 1
assert doc_api.async_client.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::

Continue with {doc}`advanced` to select components, manage them directly,
or observe individual build steps.
