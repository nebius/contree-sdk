from typing import Annotated, overload

from contree_sdk._internals.lib.decorator import post
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk._internals.lib.types import Body
from contree_sdk.api.models.instance import InstanceSpawnRequest


class InstancesMixin:
    @overload
    async def spawn_instance(self: AsyncClientMixin, request: Annotated[InstanceSpawnRequest, Body]) -> str: ...
    @overload
    def spawn_instance(self: SyncClientMixin, request: Annotated[InstanceSpawnRequest, Body]) -> str: ...
    @post("/v1/instances", json=["uuid"])
    def spawn_instance(self, request: Annotated[InstanceSpawnRequest, Body]) -> str: ...
