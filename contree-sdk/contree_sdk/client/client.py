from abc import ABC

from contree_sdk.client.v1.common import V1Mixin
from contree_sdk.lib.base import ClientBase
from contree_sdk.lib.mixins import AsyncClientMixin, SyncClientMixin


class ContreeClientBase(ClientBase, V1Mixin, ABC): ...


class ContreeClient(AsyncClientMixin, ContreeClientBase): ...


class ContreeSyncClient(SyncClientMixin, ContreeClientBase): ...
