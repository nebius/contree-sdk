# Sessions and operations

Start with {doc}`../running-commands`, {doc}`../sessions`, or {doc}`../operation`.
Sync calls return results directly. Async calls must be awaited unless used as the
`PendingRun` context described in the operation guide.

```{automodule} contree_sdk.session
:members: ContreeSession, ContreeAsyncSession, Operation, AsyncOperation, SubprocessHandle, AsyncSubprocessHandle, PendingRun
:inherited-members:
:undoc-members:
:member-order: bysource
```
