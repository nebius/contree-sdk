from dataclasses import replace

import pytest
from contree_client.models import EventDataExit

from contree_sdk.session.lazy_state import LazyState
from tests.unit.session.lazy_clients import event


@pytest.mark.parametrize("phase", ["running", "draining", "snapshotting"])
def test_vm_timeout_is_failure_even_during_snapshot(phase):
    state = LazyState(phase=phase)
    exited = event("exit", 1)
    assert isinstance(exited.data, EventDataExit)
    state.observe(replace(exited, data=replace(exited.data, timed_out=True)), None)
    assert state.phase == "failed"
    assert isinstance(state.error, TimeoutError)
    assert "execution timeout" in str(state.error)
    assert state.snapshots == 0
