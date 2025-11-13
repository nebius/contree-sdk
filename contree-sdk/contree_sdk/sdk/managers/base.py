from contree_sdk.sdk.client.base import _ContreeBase


class BaseManager:
    def __init__(self, client: _ContreeBase):
        self._client = client
