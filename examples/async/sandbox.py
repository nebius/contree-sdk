"""Run two async commands through a sandbox configured from ENV or an INI profile."""

import asyncio

from contree_client.models import StreamRepr

from contree_sdk import create_async_sandbox_session


async def main() -> None:
    async with create_async_sandbox_session(image="tag:alpine:latest") as session:
        await session.run(shell="echo 'Hello from ConTree!' > /message.txt")
        result = await session.run("cat", args=["/message.txt"])
        if isinstance(result.stdout, StreamRepr):
            print(result.stdout.as_text(), end="")


if __name__ == "__main__":
    asyncio.run(main())


def test_sandbox(sandbox_api):
    import runpy

    runpy.run_path(__file__, run_name="__main__")
    client = sandbox_api.async_client
    assert len(client.calls_for("spawn_instance")) == 1
    calls = client.calls_for("operation_subprocess_create")
    assert calls[0].args[1] == "echo 'Hello from ConTree!' > /message.txt"
    assert calls[1].args[1] == "cat"
    assert calls[1].kwargs["args"] == ["/message.txt"]
    assert len(client.calls_for("operation_subprocess_kill")) == 1
