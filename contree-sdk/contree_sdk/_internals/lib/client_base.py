from abc import ABC, abstractmethod
from typing import overload

import httpx
from httpx import Request, Response
from httpx._config import DEFAULT_TIMEOUT_CONFIG, Timeout

from contree_sdk._internals.lib.api_decorator import EMPTY
from contree_sdk._internals.lib.helpers import convert_data_to_type
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk._internals.lib.types import ApiEndpointInfo, ReturnType


class ClientBase(ABC):
    _client_class: type[httpx._client.BaseClient]

    def __init__(self, token: str, base_url: str, transport_timeout: float = DEFAULT_TIMEOUT_CONFIG.connect) -> None:
        headers = {"Authorization": f"Bearer {token}"}
        self._client = self._client_class(
            headers=headers, base_url=base_url, timeout=Timeout(timeout=transport_timeout)
        )

    def _build_request(self, endpoint_info: ApiEndpointInfo, data: dict) -> Request:
        kwargs = endpoint_info.get_files_data_by_data(data)
        return self._client.build_request(
            method=endpoint_info.method.upper(),
            url=endpoint_info.get_path_by_data(data),
            params=endpoint_info.get_query_data_by_data(data),
            json=endpoint_info.get_body_data_by_data(data),
            **kwargs,
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
        response.raise_for_status()
        if endpoint_info.json_path is None:
            if endpoint_info.return_type is str:
                return response.text
            if endpoint_info.return_type is bytes:
                return response.content
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
