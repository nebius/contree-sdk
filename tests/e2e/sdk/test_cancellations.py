from asyncio import get_event_loop, sleep
from uuid import UUID

import pytest
from pytest_mock import MockerFixture, MockType

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.client._base import _ContreeBase
from contree_sdk.sdk.exceptions import CancelledOperationError, GoneError
from tests.utils.interrupter import interrupter


IMPORT_URL = "docker://ghcr.io/linuxserver/code-server:latest"


async def _get_operation_id_from_spy(spy_obj: MockType):
    while spy_obj.called is False:
        await sleep(0.01)
    return spy_obj.call_args.kwargs["operation_uuid"]


async def _wait_cancelled(operation_id: UUID, contree: _ContreeBase):
    waiter = await contree._get_operation_waiter(operation_id)
    with pytest.raises((CancelledOperationError, GoneError)):
        await waiter.wait_for_result(operation_timeout=3)


async def test_cancel_import(contree: Contree, mocker: MockerFixture):
    spy_wait = mocker.spy(contree, "_wait_operation")

    task = get_event_loop().create_task(contree.images.pull(IMPORT_URL))
    operation_id = await _get_operation_id_from_spy(spy_wait)
    task.cancel()
    await _wait_cancelled(operation_id, contree)


async def test_cancel_import_s(contree: Contree, contree_s: ContreeSync, mocker: MockerFixture):
    spy_wait = mocker.spy(contree_s, "_wait_operation")
    with pytest.raises(KeyboardInterrupt), interrupter(0.5):
        contree_s.images.pull(IMPORT_URL)
    operation_id = spy_wait.call_args.kwargs["operation_uuid"]
    await _wait_cancelled(operation_id, contree)
