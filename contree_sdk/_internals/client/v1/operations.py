from uuid import UUID

from contree_sdk._internals.lib.api_decorator import delete, get
from contree_sdk._internals.models.operation import OperationModel


class OperationsMixin:
    @get("/v1/operations/{operation_id}", json=True)
    async def get_operation_status(self, operation_id: str | UUID) -> OperationModel: ...

    @delete("/v1/operations/{operation_id}")
    async def cancel_operation(self, operation_id: str | UUID) -> None: ...
