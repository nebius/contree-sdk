from typing import Annotated

from contree_sdk._internals.lib.api_decorator import post
from contree_sdk._internals.lib.types import Body
from contree_sdk._internals.models.instance import InstanceSpawnRequest


class InstancesMixin:
    @post("/v1/instances", json=["uuid"])
    async def spawn_instance(self, request: Annotated[InstanceSpawnRequest, Body]) -> str: ...
