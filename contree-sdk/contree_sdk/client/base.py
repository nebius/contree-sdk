from abc import ABC, abstractmethod
from typing import overload

import httpx
from httpx import Request, Response

from contree_sdk.client.decorator import EMPTY
from contree_sdk.client.helpers import convert_data_to_type
from contree_sdk.client.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk.client.types import ApiEndpointInfo, ReturnType
from contree_sdk.client.v1.common import V1Mixin


class ClientBase(ABC):
    _client_class: type[httpx._client.BaseClient]

    def __init__(self, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        self._client = self._client_class(headers=headers, base_url="https://eu-north-stage.nebius.computer")

    def _build_request(self, endpoint_info: ApiEndpointInfo, data: dict) -> Request:
        return self._client.build_request(
            method=endpoint_info.method.upper(),
            url=endpoint_info.path,
            params=data,  # todo parse real path params, query params and body params
        )

    @overload
    async def _send_request(self: AsyncClientMixin, request: Request) -> Response: ...
    @overload
    def _send_request(self: SyncClientMixin, request: Request) -> Response: ...
    @abstractmethod
    def _send_request(self, request: Request) -> Response:
        pass

    @overload
    def _parse_response(
        self,
        response: Response,
        endpoint_info: ApiEndpointInfo,
    ) -> ReturnType: ...
    def _parse_response(
        self,
        *,
        response: Response,
        endpoint_info: ApiEndpointInfo,
    ) -> ReturnType | dict | Response:
        if endpoint_info.json_path is None:
            return response

        data = response.json()
        for key in endpoint_info.json_path:
            data = data[key]
        if endpoint_info.return_type is not EMPTY:
            return convert_data_to_type(data, endpoint_info.return_type)
        return data

    @overload
    async def _handle_api_call(
        self: AsyncClientMixin, endpoint_info: ApiEndpointInfo, data: dict
    ) -> ReturnType | dict | Response: ...
    @overload
    def _handle_api_call(
        self: SyncClientMixin, endpoint_info: ApiEndpointInfo, data: dict
    ) -> ReturnType | dict | Response: ...
    @abstractmethod
    def _handle_api_call(self, endpoint_info: ApiEndpointInfo, data: dict) -> ReturnType | dict | Response: ...


class ContreeClientBase(ClientBase, V1Mixin, ABC): ...


# todo add config here
