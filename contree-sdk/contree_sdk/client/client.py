from contree_sdk.client.base import ContreeClientBase
from contree_sdk.client.mixins import AsyncClientMixin, SyncClientMixin


class ContreeClient(AsyncClientMixin, ContreeClientBase): ...


class ContreeSyncClient(SyncClientMixin, ContreeClientBase): ...
