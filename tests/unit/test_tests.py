import pytest


@pytest.mark.xfail(raises=ValueError, strict=True)
async def test_async_awaited():
    async def some_async():
        raise ValueError

    await some_async()
