from abc import ABC

from contree_sdk._internals.client.v1.common import V1Mixin
from contree_sdk._internals.lib.client_base import ClientBase
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin


class ContreeClientBase(ClientBase, V1Mixin, ABC): ...


class ContreeClient(AsyncClientMixin, ContreeClientBase): ...


class ContreeSyncClient(SyncClientMixin, ContreeClientBase): ...
