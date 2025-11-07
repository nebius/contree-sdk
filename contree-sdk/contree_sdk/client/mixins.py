from typing import TYPE_CHECKING

from httpx import AsyncClient, Client, Request, Response

from contree_sdk.client.types import ApiEndpointInfo, ReturnType

if TYPE_CHECKING:
    from contree_sdk.client.base import ClientBase


class SyncClientMixin:
    _client_class: type[Client] = Client
    _client: Client

    def _send_request(self, request: Request) -> Response:
        return self._client.send(request)

    def _handle_api_call(self, endpoint_info: ApiEndpointInfo, data: dict) -> ReturnType | dict | Response:
        self: ClientBase

        request = self._build_request(endpoint_info=endpoint_info, data=data)
        resp = self._client.send(request)
        return self._parse_response(response=resp, endpoint_info=endpoint_info)


class AsyncClientMixin:
    _client_class: type[AsyncClient] = AsyncClient
    _client: AsyncClient

    async def _send_request(self, request: Request) -> Response:
        return await self._client.send(request)

    async def _handle_api_call(self, endpoint_info: ApiEndpointInfo, data: dict) -> ReturnType | dict | Response:
        self: ClientBase

        request = self._build_request(endpoint_info=endpoint_info, data=data)
        resp = await self._client.send(request)
        return self._parse_response(response=resp, endpoint_info=endpoint_info)
