# Sessions and operations

Start with {doc}`../running-commands`, {doc}`../sessions`, or {doc}`../operation`.
Sync calls return results directly. Async calls must be awaited unless used as the
`PendingRun` context described in the operation guide.

```{eval-rst}
.. automodule:: contree_sdk.session
   :members: ContreeSession, ContreeAsyncSession, Operation, AsyncOperation, SubprocessHandle, AsyncSubprocessHandle, PendingRun, AbstractCommitPolicy, ApiSuccessCommitPolicy, ZeroExitCommitPolicy, LazySession, AsyncLazySession, AbstractSnapshotPolicy, SnapshotEvent, IdleSnapshotPolicy, CommandCountSnapshotPolicy, CompositeSnapshotPolicy
   :inherited-members:
   :undoc-members:
   :member-order: bysource
```
