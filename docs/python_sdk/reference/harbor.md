# Experimental Harbor runtime

This API describes an unfinished prototype. Its fixed VM lifetime is pending
redesign and is not the contract for a supported Harbor environment backend.

See {doc}`../../integrations/harbor/runtime` for lifecycle, timeout, ownership, and snapshot behavior.

```{eval-rst}
.. automodule:: contree_sdk.harbor.runtime
   :members: AsyncRuntime, AsyncRuntimeFactory, RuntimeOptions, ContreeAsyncRuntime, RuntimeLifecycle, ManualSnapshotPolicy, create_runtime
   :inherited-members:
   :undoc-members:
   :member-order: bysource
```
