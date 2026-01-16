from __future__ import annotations

from typing import TYPE_CHECKING

from httpx import AsyncClient, Client, Request, Response

from contree_sdk._internals.lib.types import ApiEndpointInfo, ReturnType


if TYPE_CHECKING:
    from contree_sdk._internals.lib.client_base import ClientBase


class SyncClientMixin:
    _client_class: type[Client] = Client
    _client: Client

    def _send_request(self, request: Request) -> Response:
        return self._client.send(request, follow_redirects=True)

    def _handle_api_call(self: ClientBase, endpoint_info: ApiEndpointInfo, data: dict) -> ReturnType | dict | Response:
        request = self._build_request(endpoint_info=endpoint_info, data=data)
        resp = self._send_request(request)
        return self._parse_response(response=resp, endpoint_info=endpoint_info)


class AsyncClientMixin:
    _client_class: type[AsyncClient] = AsyncClient
    _client: AsyncClient

    async def _send_request(self, request: Request) -> Response:
        resp = await self._client.send(request, follow_redirects=True, stream=True)
        try:
            await resp.aread()
        except BaseException as e:
            e.response = resp
            await resp.aclose()
            raise
        else:
            return resp

    async def _handle_api_call(
        self: ClientBase, endpoint_info: ApiEndpointInfo, data: dict
    ) -> ReturnType | dict | Response:
        request = self._build_request(endpoint_info=endpoint_info, data=data)

        resp = await self._send_request(request)
        return self._parse_response(response=resp, endpoint_info=endpoint_info)
