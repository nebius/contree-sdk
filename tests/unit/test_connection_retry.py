from contextlib import AsyncExitStack, ExitStack
from typing import Any

import httpx
import pytest
from contree_client import RetryPolicy
from contree_client.exceptions import APIStatusError
from contree_client.httpx import ContreeAsyncClient, ContreeClient
from contree_client.profiles import Profile
from contree_client.runtime import RequestSpec

from contree_sdk import create_sandbox_session
from contree_sdk.connection import ConnectionConfig
from tests.unit.session.test_sandbox_factory import FactoryAsyncClient, FactoryClient


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("setting", ["default", "custom", "disabled"])
async def test_sandbox_retry_policy_configuration(asynchronous, setting):
    policy = RetryPolicy(max_attempts=3, delays=(0,)) if setting == "custom" else None
    options: dict[str, Any] = {} if setting == "default" else {"retry": policy}
    profile = Profile(name="retry", url="https://test.invalid", token="token", auth_type="jwt")
    if asynchronous:
        async with create_sandbox_session(
            image="base", profile=profile, client_type=FactoryAsyncClient, **options
        ) as session:
            actual = session.session.client.retry
    else:
        with create_sandbox_session(image="base", profile=profile, client_type=FactoryClient, **options) as session:
            actual = session.session.client.retry
    if setting == "default":
        assert actual == RetryPolicy()
    else:
        assert actual is policy


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("policy", [None, RetryPolicy(max_attempts=2)])
async def test_sandbox_preserves_borrowed_client_retry_policy(asynchronous, policy):
    client = FactoryAsyncClient(retry=policy) if asynchronous else FactoryClient(retry=policy)
    if asynchronous:
        async with create_sandbox_session(image="base", client=client):
            assert client.retry is policy
    else:
        with create_sandbox_session(image="base", client=client):
            assert client.retry is policy
    assert client.retry is policy
    assert client.opened == client.closed == 0


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize(
    ("method", "status", "enabled", "attempts"),
    [("GET", 503, True, 2), ("GET", 503, False, 1), ("POST", 503, True, 1), ("POST", 429, True, 2)],
)
async def test_default_retry_uses_client_replay_rules(asynchronous, method, status, enabled, attempts):
    requests = []

    def respond(request):
        requests.append(request)
        code = status if len(requests) == 1 else 200
        return httpx.Response(code, headers={"Retry-After": "0"}, json={"ok": code == 200})

    profile = Profile(name="retry", url="https://test.invalid", token="token", auth_type="jwt")
    spec = RequestSpec(method=method, path="/retry-check", idempotent=method == "GET")
    options = {} if enabled else {"retry": None}
    if asynchronous:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport, AsyncExitStack() as stack:
            client = await ConnectionConfig(
                profile=profile,
                client_type=ContreeAsyncClient,
                client_kwargs={"httpx_client": transport, **options},
            ).open_async(stack)
            if attempts == 1:
                with pytest.raises(APIStatusError) as caught:
                    await client.call(spec)
                assert caught.value.status == status
            else:
                assert (await client.call(spec)).status == 200
    else:
        with httpx.Client(transport=httpx.MockTransport(respond)) as transport, ExitStack() as stack:
            client = ConnectionConfig(
                profile=profile,
                client_type=ContreeClient,
                client_kwargs={"httpx_client": transport, **options},
            ).open_sync(stack)
            if attempts == 1:
                with pytest.raises(APIStatusError) as caught:
                    client.call(spec)
                assert caught.value.status == status
            else:
                assert client.call(spec).status == 200
    assert len(requests) == attempts
