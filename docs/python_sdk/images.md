---
icon: layer-group
---

# Working with Images

Image management (resolving, importing, tagging, listing) is provided by the `contree_client` package that `contree-sdk` builds on. A `ContreeSession` accepts any resolvable image reference directly, so most workflows never need to touch these APIs — this page covers the cases where you do.

## Resolving and Importing

`client.resolve_image(ref)` resolves a `"tag:..."` reference or UUID to an image UUID, raising `NotFoundError` if it isn't imported yet. `client.import_image(registry, tag=...)` starts an import operation from an external registry; `client.wait_operation(operation_uuid)` waits for it to finish and reports the resulting image UUID.

````{tab} Async
```{literalinclude} ../../examples/images/pull_image.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/images/pull_image_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

## Tagging Images

`client.update_image_tag(image_uuid, tag)` assigns a tag; `client.delete_image_tag(image_uuid, tag=...)` removes one. Tags are unique — assigning an existing tag to a new image moves it automatically.

````{tab} Async
```{literalinclude} ../../examples/images/tag_image.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/images/tag_image_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

## Listing Images

`client.list_images(*, limit=None, offset=None, tagged=False, tag=None, uuid=None, since=None, until=None)` returns an `ImageListResponse` with an `.images` list.

````{tab} Async
```{literalinclude} ../../examples/images/list_images.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/images/list_images_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

## Using an Image in a Session

Once you have a tag or UUID, hand it to `ContreeSession`/`ContreeAsyncSession` directly — resolution happens lazily on the first `.run()` call, so no separate "use" step is needed:

```python
session = ContreeSession(client, image="tag:python:3.11-slim")
```

See {doc}`getting-started` for the full session walkthrough.
