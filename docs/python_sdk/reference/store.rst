:icon: database

Store
=====

A session's durable history is a DAG of images with named branch pointers,
persisted through a :class:`SyncStore`/:class:`AsyncStore` implementation.
Pick the variant that matches your client: :class:`ContreeSession` (sync)
takes a :class:`SyncStore`, :class:`ContreeAsyncSession` takes an
:class:`AsyncStore`.

.. automodule:: contree_sdk.store
   :members: HistoryEntry, SyncStore, AsyncStore, SyncMemoryStore, AsyncMemoryStore, SyncSQLiteStore, AsyncSQLiteStore
   :inherited-members:
   :undoc-members:
   :member-order: bysource
