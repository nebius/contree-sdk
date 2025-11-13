from abc import ABC

from contree_sdk.api.client.v1.common import V1Mixin
from contree_sdk.api.lib.base import ClientBase
from contree_sdk.api.lib.mixins import AsyncClientMixin, SyncClientMixin


class ContreeClientBase(ClientBase, V1Mixin, ABC): ...


class ContreeClient(AsyncClientMixin, ContreeClientBase): ...


class ContreeSyncClient(SyncClientMixin, ContreeClientBase): ...
