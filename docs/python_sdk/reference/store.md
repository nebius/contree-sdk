# History stores

See {doc}`../sessions` for persistence and {doc}`../branching` for navigation.
Use sync stores with `ContreeSession` and async stores with `ContreeAsyncSession`.
Stores contain image references and history, not remote filesystem data.

```{automodule} contree_sdk.store
:members: HistoryEntry, SessionMetadata, SyncStore, AsyncStore, SyncMemoryStore, AsyncMemoryStore, SyncSQLiteStore, AsyncSQLiteStore
:inherited-members:
:undoc-members:
:member-order: bysource
```
