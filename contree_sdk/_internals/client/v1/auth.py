from contree_sdk._internals.lib.api_decorator import get
from contree_sdk.utils.models.auth import WhoAmI


class AuthMixin:
    @get("/v1/whoami", json=True)
    async def whoami(self) -> WhoAmI: ...
