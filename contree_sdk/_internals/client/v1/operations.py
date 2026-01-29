from typing import overload
from uuid import UUID

from contree_sdk._internals.lib.api_decorator import delete, get
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk._internals.models.operation import OperationModel


class OperationsMixin:
    @overload
    async def get_operation_status(self: AsyncClientMixin, operation_id: str | UUID) -> OperationModel: ...
    @overload
    def get_operation_status(self: SyncClientMixin, operation_id: str | UUID) -> OperationModel: ...

    @get("/v1/operations/{operation_id}", json=True)
    def get_operation_status(self, operation_id: str | UUID) -> OperationModel: ...

    @overload
    async def cancel_operation(self: AsyncClientMixin, operation_id: str | UUID) -> None: ...
    @overload
    def cancel_operation(self: SyncClientMixin, operation_id: str | UUID) -> None: ...

    @delete("/v1/operations/{operation_id}")
    def cancel_operation(self, operation_id: str | UUID) -> None: ...
