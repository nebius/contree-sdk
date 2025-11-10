from abc import ABC

from contree_sdk.client.base import ClientBase
from contree_sdk.client.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk.client.v1.common import V1Mixin


class ContreeClientBase(ClientBase, V1Mixin, ABC): ...


class ContreeClient(AsyncClientMixin, ContreeClientBase): ...


class ContreeSyncClient(SyncClientMixin, ContreeClientBase): ...
