from __future__ import annotations

from dataclasses import dataclass
from enum import auto
from typing import TYPE_CHECKING, ClassVar, TypeAlias, TypeVar

from strenum import StrEnum


if TYPE_CHECKING:
    from contree_sdk._internals.io.operation_waiter import OperationWaiter
    from contree_sdk._internals.io.wiring import OperationOutputs
    from contree_sdk.sdk.objects.image_like.result import ContreeResult
    from contree_sdk.sdk.objects.run import RunRequest


# todo use it and use _state_lock inside image like
class ImageState(StrEnum):
    PULLED = auto()  # when pulled from ConTree
    PREPARING = auto()  # started to configure run
    PREPARED = auto()  # configured run
    EXECUTING = auto()  # started to execute run

    SUCCEEDED = auto()  # received success result
    FAILED = auto()  # received fail result


@dataclass
class _WithRequest:
    request: RunRequest


@dataclass
class _Pulled:
    state: ClassVar[ImageState] = ImageState.PULLED


@dataclass
class _Prepared(_WithRequest):
    state: ClassVar[ImageState] = ImageState.PREPARED


@dataclass
class _Executing(_WithRequest):
    state: ClassVar[ImageState] = ImageState.EXECUTING

    waiter: OperationWaiter
    outputs: OperationOutputs
    timeout: float


@dataclass
class _Succeeded(_WithRequest):
    state: ClassVar[ImageState] = ImageState.SUCCEEDED

    result: ContreeResult


@dataclass
class _Failed(_WithRequest):
    state: ClassVar[ImageState] = ImageState.FAILED


StateData: TypeAlias = _Pulled | _Prepared | _Executing | _Succeeded | _Failed
StateDataT = TypeVar("StateDataT", bound=StateData)

_PREPARATION_STATES = frozenset({ImageState.PREPARING, ImageState.PREPARED})

"""
Permitted state transitions.

Mapping:
    from_state -> allowed to_states
"""
STATE_MACHINE: dict[ImageState, frozenset[ImageState]] = {
    ImageState.PULLED: _PREPARATION_STATES,
    ImageState.PREPARING: _PREPARATION_STATES,
    ImageState.PREPARED: frozenset({ImageState.PREPARED, ImageState.EXECUTING}),
    ImageState.EXECUTING: frozenset({ImageState.SUCCEEDED, ImageState.FAILED}),
    ImageState.SUCCEEDED: _PREPARATION_STATES,
}
