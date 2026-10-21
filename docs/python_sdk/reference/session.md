# Sessions and operations

Start with {doc}`../session-model`, {doc}`../sessions`, or {doc}`../operation`.
Sync calls return results directly. Async calls must be awaited unless used as the
`PendingRun` context described in the operation guide.

`ContreeSession` and `ContreeAsyncSession` save each command by default.
`disposable=True` leaves the session image unchanged. `LazySession` and
`AsyncLazySession` reuse a VM until snapshot. Snapshots are lightweight and can
run after every command, but they stop the VM. An unchanged filesystem can return
the same image UUID. Lazy `inspect()` never snapshots or stops a VM; it raises
while a VM is active. Call `snapshot()` first to inspect the saved image.
See [Save after every command](../session-model.md#save-after-every-command).

```{eval-rst}
.. automodule:: contree_sdk.session
   :members: ContreeSession, ContreeAsyncSession, Operation, AsyncOperation, SubprocessHandle, AsyncSubprocessHandle, PendingRun, AbstractCommitPolicy, ApiSuccessCommitPolicy, ZeroExitCommitPolicy, LazySession, AsyncLazySession, AbstractSnapshotPolicy, SnapshotEvent, ManualSnapshotPolicy, IdleSnapshotPolicy, CommandCountSnapshotPolicy, CompositeSnapshotPolicy
   :inherited-members:
   :undoc-members:
   :member-order: bysource
```
