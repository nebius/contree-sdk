"""Fetch a URL for `ADD <url>` directives.

`http_fetch` is a pluggable `(url, method, headers) -> (headers, body)`
callable so callers can swap in their own HTTP stack; the default
implementation uses only the stdlib (`urllib.request`), no third-party
dependency. Deduplication against a previously-uploaded file happens one
layer up, in `contree_sdk.cache.SyncCache`/`AsyncCache`, keyed by the response `ETag`.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from collections.abc import AsyncIterable, Iterable
from typing import TypeAlias


USER_AGENT = "contree-sdk url-fetch"
FETCH_TIMEOUT_DEFAULT = 300.0

FetchResponse: TypeAlias = tuple[Iterable[tuple[str, str]], Iterable[bytes]]
AsyncFetchResponse: TypeAlias = tuple[Iterable[tuple[str, str]], AsyncIterable[bytes]]


def http_fetch(url: str, method: str, headers: Iterable[tuple[str, str]]) -> FetchResponse:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"unsupported URL scheme: {url!r}")
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    request_headers.update(headers)
    request = urllib.request.Request(url, method=method, headers=request_headers)  # noqa: S310
    response = urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_DEFAULT)  # noqa: S310
    return list(response.headers.items()), response


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def url_basename(url: str, fallback: str = "downloaded") -> str:
    parsed = urllib.parse.urlsplit(url)
    name = parsed.path.rsplit("/", 1)[-1]
    return name or fallback


# http_fetch_async implementations chooser. Each keeps its client/response
# alive for the body generator's lifetime (closing only once the caller has
# fully drained it or abandoned iteration) - exiting the client's `async
# with` block before that point would tear down the connection mid-stream.
try:
    import aiohttp

    async def http_fetch_async(url: str, method: str, headers: Iterable[tuple[str, str]]) -> AsyncFetchResponse:
        session = aiohttp.ClientSession(headers=dict(headers))
        try:
            response = await session.request(method, url)
            response.raise_for_status()
        except BaseException:
            await session.close()
            raise
        response_headers = list(response.headers.items())

        async def body() -> AsyncIterable[bytes]:
            try:
                async for chunk in response.content.iter_any():
                    yield chunk
            finally:
                await session.close()

        return response_headers, body()

except ImportError:
    try:
        import httpx

        async def http_fetch_async(url: str, method: str, headers: Iterable[tuple[str, str]]) -> AsyncFetchResponse:
            client = httpx.AsyncClient(headers=dict(headers))
            try:
                request = client.build_request(method, url)
                response = await client.send(request, stream=True)
                response.raise_for_status()
            except BaseException:
                await client.aclose()
                raise
            response_headers = list(response.headers.items())

            async def body() -> AsyncIterable[bytes]:
                try:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                finally:
                    await response.aclose()
                    await client.aclose()

            return response_headers, body()

    except ImportError:

        async def http_fetch_async(url: str, method: str, headers: Iterable[tuple[str, str]]) -> AsyncFetchResponse:
            raise RuntimeError(
                "no async HTTP client available; "
                "install aiohttp or httpx or provide your own `http_fetch_async` implementation"
            )
