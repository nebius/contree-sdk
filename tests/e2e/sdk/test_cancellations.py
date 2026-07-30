import asyncio
from asyncio import get_event_loop, sleep, wait_for

import pytest
from pytest_mock import MockerFixture, MockType

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage
from tests.utils.interrupter import interrupter


IMPORT_URL = "docker://ghcr.io/linuxserver/code-server:latest"


async def _get_operation_id_from_spy(spy_obj: MockType):
    while spy_obj.called is False:
        await sleep(0.01)
    return spy_obj.call_args.kwargs["operation_uuid"]


async def _wait_cancel_requested(spy_obj: MockType):
    for _ in range(300):
        if spy_obj.called:
            return
        await sleep(0.01)
    raise AssertionError("cancel_operation was not requested")


async def test_cancel_import(contree: Contree, mocker: MockerFixture):
    spy_wait = mocker.spy(contree, "_wait_operation")
    spy_cancel = mocker.spy(contree._api, "cancel_operation")

    task = get_event_loop().create_task(contree.images.pull(IMPORT_URL))
    operation_id = await _get_operation_id_from_spy(spy_wait)
    task.cancel()

    await _wait_cancel_requested(spy_cancel)
    assert spy_cancel.call_args.args[0] == str(operation_id)


async def test_cancel_import_s(contree_s: ContreeSync, mocker: MockerFixture):
    spy_wait = mocker.spy(contree_s, "_wait_operation")
    spy_cancel = mocker.spy(contree_s._api, "cancel_operation")

    with pytest.raises(KeyboardInterrupt), interrupter(0.5):
        contree_s.images.pull(IMPORT_URL)

    operation_id = spy_wait.call_args.kwargs["operation_uuid"]
    await _wait_cancel_requested(spy_cancel)
    assert spy_cancel.call_args.args[0] == str(operation_id)


async def test_timed_out_wait_cancels_operation(contree: Contree, image: ContreeImage, mocker: MockerFixture):
    spy_waiter = mocker.spy(contree, "_get_operation_waiter")
    spy_cancel = mocker.spy(contree._api, "cancel_operation")
    started = await image.run(shell="sleep 60", timeout=60).start()

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await wait_for(started, timeout=2)

    await _wait_cancel_requested(spy_cancel)
    assert spy_cancel.call_args.args[0] == str(spy_waiter.call_args.args[0])
