from contree_client.models import OperationEventType

from contree_sdk import Contree
from contree_sdk.sdk.objects.image import ContreeImage


async def test_stream_operation_events(contree: Contree, image: ContreeImage):
    response = await contree.api.spawn_instance("echo streamed", str(image.uuid), shell=True)
    operation_id = response.uuid

    events = [event async for event in contree.api.follow_operation_events(operation_id)]

    assert events
    ids = [event.id for event in events]
    assert ids == sorted(ids)
    assert events[-1].type == OperationEventType.COMPLETION

    since = ids[0]
    tail = [event async for event in contree.api.follow_operation_events(operation_id, since=since)]
    assert [event.id for event in tail] == [event_id for event_id in ids if event_id > since]
