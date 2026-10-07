# SDK exceptions

See {doc}`../troubleshooting` for recovery scenarios. Client API errors, transport
errors, `InterruptedError`, and validation errors can also propagate. A nonzero
process exit code is returned in `InstanceResult`, not raised as an SDK exception.

```{eval-rst}
.. automodule:: contree_sdk.exceptions
   :members: FailedOperationError, SessionConflictError, DockerBuildError
   :inherited-members:
   :undoc-members:
   :member-order: bysource
```
