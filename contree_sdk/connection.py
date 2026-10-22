"""Shared connection resolution and ownership for public SDK factories."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from contree_client import profiles
from contree_client.profiles import Profile
from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.session.cleanup import await_cleanup


def profile_from_args(
    *, token: str, url: str | None = None, project: str | None = None, auth_type: Literal["iam", "jwt"] = "iam"
) -> Profile:
    """Build an explicit client profile without reading or writing configuration.

    The default configuration uses the client's endpoint when URL is omitted.

    Returns:
        A regular contree-client Profile.

    Raises:
        ValueError: Credentials, URL, or authentication type are invalid.

    """
    if auth_type not in {"iam", "jwt"}:
        raise ValueError("auth_type must be 'iam' or 'jwt'")
    if not token or not token.strip():
        raise ValueError("token must not be empty")
    if url is None and auth_type == "iam":
        url = profiles.DEFAULT_IAM_URL
    if not url or not url.strip():
        raise ValueError("url is required for JWT authentication")
    return Profile(name="explicit", url=url, token=token, project=project, auth_type=auth_type)


@dataclass
class ConnectionConfig:
    url: str | None = None
    project: str | None = None
    token: str | None = field(default=None, repr=False)
    auth_type: Literal["iam", "jwt"] | None = None
    profile: Profile | str | None = None
    config_path: str | Path | None = None
    client: ContreeSyncClient | ContreeAsyncClient | None = None
    client_type: type[ContreeSyncClient | ContreeAsyncClient] | None = None
    client_kwargs: dict[str, Any] = field(default_factory=dict, repr=False)

    def resolve_profile(self) -> Profile:
        if any(value is not None for value in (self.url, self.project, self.token, self.auth_type)):
            if self.profile is not None or self.config_path is not None:
                raise ValueError("connection arguments cannot be combined with profile or config_path")
            return profile_from_args(
                token=self.token or "", url=self.url, project=self.project, auth_type=self.auth_type or "iam"
            )
        if isinstance(self.profile, Profile):
            if self.config_path is not None:
                raise ValueError("a Profile object cannot be combined with config_path")
            return self.profile
        if self.profile is not None or self.config_path is not None:
            return profiles.resolve_profile(self.profile, path=self.config_path)
        return profiles.from_env() or profiles.resolve_profile()

    def validate(self, *, asynchronous: bool) -> None:
        mode = "async with" if asynchronous else "with"
        contract = ContreeAsyncClient if asynchronous else ContreeSyncClient
        if self.client_type is not None and (
            not isinstance(self.client_type, type) or not issubclass(self.client_type, contract)
        ):
            raise TypeError(f"client_type must be a compatible client class for {mode}")
        if self.client is not None and not isinstance(self.client, contract):
            raise TypeError(f"client must implement the client interface for {mode}")
        if self.client is not None and (
            self.client_kwargs
            or any(
                value is not None
                for value in (
                    self.client_type,
                    self.profile,
                    self.config_path,
                    self.url,
                    self.project,
                    self.token,
                    self.auth_type,
                )
            )
        ):
            raise ValueError("client cannot be combined with client_type or connection settings")
        if "base_url" in self.client_kwargs:
            raise ValueError("use url or profile instead of base_url")

    def open_sync(self, stack: ExitStack) -> ContreeSyncClient:
        self.validate(asynchronous=False)
        if self.client is not None:
            return cast("ContreeSyncClient", self.client)
        client_type = cast("type[ContreeSyncClient] | None", self.client_type)
        if client_type is None:
            from contree_client.httpx import ContreeClient

            client_type = ContreeClient
        client = client_type.from_profile(self.resolve_profile(), **self.client_kwargs)
        stack.callback(client.close)
        client.open()
        return client

    async def open_async(self, stack: AsyncExitStack) -> ContreeAsyncClient:
        self.validate(asynchronous=True)
        if self.client is not None:
            return cast("ContreeAsyncClient", self.client)
        client_type = cast("type[ContreeAsyncClient] | None", self.client_type)
        if client_type is None:
            from contree_client.aiohttp import ContreeAsyncClient

            client_type = ContreeAsyncClient
        client = client_type.from_profile(self.resolve_profile(), **self.client_kwargs)
        stack.push_async_callback(client.close)
        await client.open()
        return client


@contextmanager
def owned_resources() -> Iterator[ExitStack]:
    """Close resources while preserving the primary error.

    Yields:
        A stack for resources created by a helper.

    """
    stack = ExitStack()
    try:
        yield stack
    except BaseException:
        with suppress(Exception):
            stack.close()
        raise
    else:
        stack.close()


@asynccontextmanager
async def owned_resources_async() -> AsyncIterator[AsyncExitStack]:
    """Join cleanup despite repeated cancellation.

    Yields:
        A stack for resources created by an async helper.

    """
    stack = AsyncExitStack()
    try:
        yield stack
    except BaseException:
        with suppress(Exception, asyncio.CancelledError):
            await await_cleanup(stack.aclose())
        raise
    else:
        await await_cleanup(stack.aclose())
