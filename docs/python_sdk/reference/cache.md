# Build caches

Builders use caches for file-upload and URL-download metadata. Layer history lives
in the build store. See {doc}`../building-images`. SQLite cache values must be JSON-serializable.

```{automodule} contree_sdk.cache
:members: SyncCache, AsyncCache, SyncMemoryCache, AsyncMemoryCache, SyncSQLiteCache, AsyncSQLiteCache
:inherited-members:
:undoc-members:
:member-order: bysource
```
