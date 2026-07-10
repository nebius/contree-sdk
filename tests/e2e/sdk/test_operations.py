from pytest_mock import MockerFixture

from contree_sdk import Contree
from contree_sdk._internals.models.operation import OperationEventType
from contree_sdk.sdk.objects.image import ContreeImage


async def test_stream_operation_events(contree: Contree, image: ContreeImage, mocker: MockerFixture):
    spy_wait = mocker.spy(contree, "_wait_operation")
    await image.run(shell="echo streamed")
    operation_id = spy_wait.call_args.args[0]

    events = [event async for event in contree._api.stream_operation_events(operation_id)]

    assert events
    ids = [event.id for event in events]
    assert ids == sorted(ids)
    assert events[-1].type == OperationEventType.COMPLETION

    since = ids[0]
    tail = [event async for event in contree._api.stream_operation_events(operation_id, since=since)]
    assert [event.id for event in tail] == [event_id for event_id in ids if event_id > since]
