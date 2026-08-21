class FailedOperationError(Exception):
    """An operation reached a terminal non-SUCCESS status with no result at all.

    A nonzero exit code is a normal `ContreeResult`, not an error - this is
    only raised for an operation-level failure (e.g. the VM couldn't start).
    """

    def __init__(self, operation_uuid: str, error: str | None) -> None:
        super().__init__(f"operation {operation_uuid} failed: {error}")
        self.operation_uuid = operation_uuid
        self.error = error
