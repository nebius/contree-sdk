---
icon: layer-group
---

# Find, import, and name images

A session starts from an image already available on its ConTree endpoint.
`image=` accepts a UUID, `tag:NAME`, or a bare tag name. A registry URL is not a
session image reference; import it first. Image-management methods belong to
`contree-client`, which is installed with the SDK.

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

## Import a base image

Set `CONTREE_TOKEN` and `CONTREE_URL` as described in {doc}`getting-started`.
This example imports a BusyBox image through the Docker Hub mirror and assigns
the ConTree tag `tutorial-base`. The registry must be reachable by the server.

::::{tab} Sync

<!--
name: test_import_image; fixtures: doc_api, capsys
```python
doc_api.complete()
for client in (doc_api.sync, doc_api.async_client):
    client.mock("import_image", "operation-1")
```
-->

```python
import os
from contree_client.models import ImageImportRegistry, OperationStatus
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    operation_id = client.import_image(
        ImageImportRegistry(url="docker://mirror.gcr.io/library/busybox:1.37"),
        tag="tutorial-base",
    )
    response = client.wait_operation(operation_id)
    if response.status != OperationStatus.SUCCESS or not isinstance(response.result_image_uuid, str):
        raise RuntimeError(f"Image import failed: {response.error}")
    session = ContreeSession(client, image=response.result_image_uuid)
    print(response.result_image_uuid)
```

<!--
name: test_import_image
```python
assert capsys.readouterr().out == "image-1\n"
```
-->

::::
::::{tab} Async

<!--
name: async test_import_image_async; fixtures: doc_api, capsys
```python
doc_api.complete()
for client in (doc_api.sync, doc_api.async_client):
    client.mock("import_image", "operation-1")
```
-->

```python
import os
from contree_client.models import ImageImportRegistry, OperationStatus
from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    operation_id = await client.import_image(
        ImageImportRegistry(url="docker://mirror.gcr.io/library/busybox:1.37"),
        tag="tutorial-base",
    )
    response = await client.wait_operation(operation_id)
    if response.status != OperationStatus.SUCCESS or not isinstance(response.result_image_uuid, str):
        raise RuntimeError(f"Image import failed: {response.error}")
    session = ContreeAsyncSession(client, image=response.result_image_uuid)
    print(response.result_image_uuid)
```

<!--
name: test_import_image_async
```python
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

After a successful import, set `CONTREE_IMAGE="tag:tutorial-base"` for the other
guides. Registry tags and ConTree tags are separate names. Importing the same
registry reference later can produce a different image if the registry tag changed.
Use an image UUID when you need to select a specific imported image.

The sync session resolves a tag during construction. The async session resolves it
on first use or `ensure_ready()`. Resolving an unknown tag raises the client's
`NotFoundError`; session construction does not automatically import it.

## Tag a saved result

A tag gives another workflow a name for an image. Assigning an existing tag moves
it to the new image; it does not copy a session's history or defaults.

::::{tab} Sync

<!--
name: test_tag_image; fixtures: doc_api, capsys
```python
doc_api.complete()
for client in (doc_api.sync, doc_api.async_client):
    client.mock("update_image_tag", None)
```
-->

```python
import os

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    session.run(shell="echo ready > /ready.txt", disposable=False)
    client.update_image_tag(session.image_uuid, "prepared-base")
    print(session.image_uuid)
```

<!--
name: test_tag_image
```python
assert doc_api.sync.calls_for("update_image_tag")[0].args == ("image-1", "prepared-base")
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_tag_image_async; fixtures: doc_api, capsys
```python
doc_api.complete()
for client in (doc_api.sync, doc_api.async_client):
    client.mock("update_image_tag", None)
```
-->

```python
import os

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    await session.run(shell="echo ready > /ready.txt", disposable=False)
    await client.update_image_tag(session.image_uuid, "prepared-base")
    print(session.image_uuid)
```

<!--
name: test_tag_image_async
```python
assert doc_api.async_client.calls_for("update_image_tag")[0].args == ("image-1", "prepared-base")
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

Use `client.list_images(tagged=True)` to list tagged images. The response exposes
an `images` collection. `client.delete_image_tag(image_uuid, tag="prepared-base")`
removes that name. Await these methods when using `ContreeAsyncClient`.

Deleting an image on the server can invalidate stored session history. Closing a
session's client or local store does not itself delete the server image.
