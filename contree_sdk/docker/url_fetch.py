"""Fetch a URL for `ADD <url>` directives.

`http_fetch` is a pluggable `(url, method, headers) -> (status, headers, body)`
callable so callers can swap in their own HTTP stack; the default
implementation uses only the stdlib (`urllib.request`), no third-party
dependency. The status code lets callers issue conditional GETs
(`If-None-Match`/`If-Modified-Since`) and recognize a `304 Not Modified`
response (empty body) without treating it as an error. Deduplication against
a previously-uploaded file happens one layer up, in
`contree_sdk.cache.SyncCache`/`AsyncCache`, keyed by the URL and validated by
the response `ETag`/`Last-Modified`.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterable, Iterable
from typing import TypeAlias


USER_AGENT = "contree-sdk url-fetch"
FETCH_TIMEOUT_DEFAULT = 300.0
HTTP_NOT_MODIFIED = 304

FetchResponse: TypeAlias = tuple[int, Iterable[tuple[str, str]], Iterable[bytes]]
AsyncFetchResponse: TypeAlias = tuple[int, Iterable[tuple[str, str]], AsyncIterable[bytes]]


def http_fetch(url: str, method: str, headers: Iterable[tuple[str, str]]) -> FetchResponse:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"unsupported URL scheme: {url!r}")
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    request_headers.update(headers)
    request = urllib.request.Request(url, method=method, headers=request_headers)  # noqa: S310
    try:
        response = urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_DEFAULT)  # noqa: S310
    except urllib.error.HTTPError as exc:
        if exc.code == HTTP_NOT_MODIFIED:
            return exc.code, list(exc.headers.items()), iter(())
        raise
    return response.status, list(response.headers.items()), response


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
# Neither aiohttp's nor httpx's `raise_for_status()` treats a 3xx response
# (including 304) as an error - only 4xx/5xx - so a 304 flows through with
# its (empty) body and status code intact.
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
        status = response.status
        response_headers = list(response.headers.items())

        async def body() -> AsyncIterable[bytes]:
            try:
                async for chunk in response.content.iter_any():
                    yield chunk
            finally:
                await session.close()

        return status, response_headers, body()

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
            status = response.status_code
            response_headers = list(response.headers.items())

            async def body() -> AsyncIterable[bytes]:
                try:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                finally:
                    await response.aclose()
                    await client.aclose()

            return status, response_headers, body()

    except ImportError:

        async def http_fetch_async(url: str, method: str, headers: Iterable[tuple[str, str]]) -> AsyncFetchResponse:
            raise RuntimeError(
                "no async HTTP client available; "
                "install aiohttp or httpx or provide your own `http_fetch_async` implementation"
            )
