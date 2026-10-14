# SDK exceptions

See {doc}`../troubleshooting` for recovery scenarios. Client API errors, transport
errors, `InterruptedError`, and validation errors can also propagate. A nonzero
process exit code is returned in `InstanceResult` by command execution.
`write_file()` raises `FileWriteError` if its write command does not confirm success.

```{eval-rst}
.. automodule:: contree_sdk.exceptions
   :members: FailedOperationError, SessionConflictError, DockerBuildError, FileWriteError
   :inherited-members:
   :undoc-members:
   :member-order: bysource
```
