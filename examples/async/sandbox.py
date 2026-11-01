"""Run two async commands through a sandbox configured from ENV or an INI profile."""

import asyncio

from contree_sdk import create_async_sandbox_session
from contree_sdk.session.lazy_async import AsyncLazySession


async def main() -> None:
    async with create_async_sandbox_session(image="tag:alpine:latest", session_type=AsyncLazySession) as session:
        await session.run(shell="echo 'Hello from ConTree!' > /message.txt")
        result = await session.run("cat", args=["/message.txt"])
        print(result.stdout)


if __name__ == "__main__":
    asyncio.run(main())


def test_sandbox(sandbox_api, capsys):
    import runpy

    runpy.run_path(__file__, run_name="__main__")
    client = sandbox_api.async_client
    assert len(client.calls_for("spawn_instance")) == 1
    calls = client.calls_for("operation_subprocess_create")
    assert calls[0].args[1] == "echo 'Hello from ConTree!' > /message.txt"
    assert calls[1].args[1] == "cat"
    assert calls[1].kwargs["args"] == ["/message.txt"]
    assert len(client.calls_for("operation_subprocess_kill")) == 1
    assert capsys.readouterr().out == "Hello from ConTree!\n\n"
