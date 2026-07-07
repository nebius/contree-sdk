from asyncio import get_running_loop

from httpx import AsyncClient, Request, Response
from httpx._config import DEFAULT_TIMEOUT_CONFIG, Timeout

from contree_sdk._internals.lib.helpers import convert_data_to_type
from contree_sdk._internals.lib.types import EMPTY, ApiEndpointInfo, ReturnType
from contree_sdk._internals.utils.config import build_user_agent
from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.auth import IAMAuth, JWTAuth


class ClientBase:
    def __init__(
        self,
        auth: IAMAuth | JWTAuth,
        transport_timeout: float = DEFAULT_TIMEOUT_CONFIG.connect or 5.0,
    ) -> None:
        self._client_headers = {"User-Agent": build_user_agent(), **auth.get_headers()}
        self._client_base_url = auth.base_url
        self._client_timeout = Timeout(timeout=transport_timeout)
        self._client_per_loop: dict = {}

    @property
    def _client(self) -> AsyncClient:
        try:
            loop = get_running_loop()
        except RuntimeError:
            loop = None
        if loop not in self._client_per_loop:
            self._client_per_loop[loop] = AsyncClient(
                headers=self._client_headers,
                base_url=self._client_base_url,
                timeout=self._client_timeout,
            )
        return self._client_per_loop[loop]

    def _build_request(self, endpoint_info: ApiEndpointInfo, data: dict) -> Request:
        kwargs = endpoint_info.get_file_upload_kwargs(data)
        return self._client.build_request(
            method=endpoint_info.method.upper(),
            url=endpoint_info.get_path_by_data(data),
            params=endpoint_info.get_query_data_by_data(data),
            json=endpoint_info.get_body_data_by_data(data),
            **kwargs,
        )

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

    @staticmethod
    def _parse_response(
        *,
        response: Response,
        endpoint_info: ApiEndpointInfo,
    ) -> ReturnType | dict | Response | str | bytes:
        response.raise_for_status()
        if endpoint_info.json_path is None:
            if endpoint_info.return_type is str:
                return response.text
            if endpoint_info.return_type is bytes:
                return response.content
            return response

        if not response.text:
            return response.text
        data = response.json()
        for key in endpoint_info.json_path:
            data = data[key]
        if endpoint_info.return_type is not EMPTY:
            return convert_data_to_type(data, endpoint_info.return_type)
        return data

    async def _handle_api_call(
        self, endpoint_info: ApiEndpointInfo, data: dict
    ) -> ReturnType | dict | Response | str | bytes:
        with wrap_api_call():
            request = self._build_request(endpoint_info=endpoint_info, data=data)
            resp = await self._send_request(request)
            return self._parse_response(response=resp, endpoint_info=endpoint_info)
