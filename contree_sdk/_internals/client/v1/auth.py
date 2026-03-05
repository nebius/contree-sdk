from typing import overload

from contree_sdk._internals.lib.api_decorator import get
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk.utils.models.auth import WhoAmI


class AuthMixin:
    @overload
    async def whoami(self: AsyncClientMixin) -> WhoAmI: ...
    @overload
    def whoami(self: SyncClientMixin) -> WhoAmI: ...

    @get("/v1/whoami", json=True)
    def whoami(self) -> WhoAmI: ...
