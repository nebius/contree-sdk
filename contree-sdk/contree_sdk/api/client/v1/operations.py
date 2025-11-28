from typing import overload

from contree_sdk.api.lib.decorator import get
from contree_sdk.api.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk.api.models.operation import OperationModel


class OperationsMixin:
    @overload
    async def get_operation_status(self: AsyncClientMixin, operation_id: str) -> OperationModel: ...
    @overload
    def get_operation_status(self: SyncClientMixin, operation_id: str) -> OperationModel: ...

    @get("/v1/operations/{operation_id}", json=True)
    def get_operation_status(self, operation_id: str) -> OperationModel: ...
