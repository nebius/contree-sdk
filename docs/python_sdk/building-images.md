---
icon: file-code
---

# Build a Docker image

Use `sync_build_image` or `async_build_image` when your setup lives in a Dockerfile.
You need a Dockerfile, any local files referenced by `COPY` or `ADD`, and a
configured ConTree connection. No Docker installation, Docker daemon, or Docker API
access is required.

The SDK translates supported Dockerfile instructions into ConTree image layers
and executes build commands on ConTree. The result is a ConTree filesystem image
UUID that you can pass to `create_sandbox_session`.

Use that image as a prepared baseline, then try changes on session branches.
{doc}`Work with a Session <session-model>` explains snapshots, rollback, and
resuming saved work without rebuilding the baseline.

Build caching is enabled by default. Later builds reuse layers whose instructions
and inputs have not changed. If you change an instruction, a source file, or the
base image, the SDK rebuilds the affected layers. You do not need to rebuild
unchanged layers each time you start your application.

## Create a small build context

Configure a connection as described in {ref}`sandbox-connection`. For
`FROM alpine:latest`, the builder first resolves the image in ConTree. If it is
missing, the builder imports it from Docker Hub. This fallback belongs to
Dockerfile builds; `create_sandbox_session` requires an existing ConTree image.

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

`session_id` selects the build's cached layer history in the Store. Within that
history, each layer is identified by a hash of its instruction, inputs, and
preceding state. Reusing a session ID lets later builds find matching layers;
changing it starts a separate build history.

The default ID derives from the context path and connection scope. Supply a
stable `session_id=` to keep the same build history after moving the context.
Avoid concurrent builds that mutate the same build session.

| Component  | What it records                                           |
| ---------- | --------------------------------------------------------- |
| `storage=` | History and branch pointers used to reuse built layers.   |
| `cache=`   | Uploaded-file and URL-download metadata used by COPY/ADD. |

The helpers use SQLite by default in `$XDG_CACHE_HOME/contree/`, with
`~/.cache/contree/` as the fallback. Build history is stored in `builds.sqlite3`;
upload metadata is stored in `images.sqlite3`. Set `cache_dir=` to change the directory.
Keep referenced images and uploaded files
available on the server. `no_cache=True` disables layer reuse; it does not force
identical file content to be uploaded again.

For a workflow that imports, builds, and runs with one connection, see
{ref}`shared-image-client` in {doc}`advanced`.

Continue with {doc}`advanced` to select components, manage them directly,
or observe individual build steps.
