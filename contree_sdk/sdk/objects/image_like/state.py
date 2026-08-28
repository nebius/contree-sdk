from __future__ import annotations

from dataclasses import dataclass
from enum import auto
from typing import TYPE_CHECKING, Any, ClassVar, TypeAlias, TypeVar

from strenum import StrEnum


if TYPE_CHECKING:
    from contree_sdk.sdk.io.wiring import OperationOutputs
    from contree_sdk.sdk.objects.image_like.result import ContreeResult
    from contree_sdk.sdk.objects.run import RunRequest


# todo use it and use a state lock inside image like
class ImageState(StrEnum):
    PULLED = auto()  # when pulled from ConTree
    PREPARING = auto()  # started to configure run
    PREPARED = auto()  # configured run
    EXECUTING = auto()  # started to execute run

    SUCCEEDED = auto()  # received success result
    FAILED = auto()  # received fail result


@dataclass
class WithRequest:
    request: RunRequest


@dataclass
class Pulled:
    state: ClassVar[ImageState] = ImageState.PULLED


@dataclass
class Prepared(WithRequest):
    state: ClassVar[ImageState] = ImageState.PREPARED


@dataclass
class Executing(WithRequest):
    state: ClassVar[ImageState] = ImageState.EXECUTING

    # typed loosely: sync and async image-like objects use their own,
    # differently-shaped waiter (`waiter_sync.OperationWaiter` /
    # `waiter_async.OperationWaiter`); this dataclass is shared by both.
    waiter: Any
    outputs: OperationOutputs
    timeout: float


@dataclass
class Succeeded(WithRequest):
    state: ClassVar[ImageState] = ImageState.SUCCEEDED

    result: ContreeResult


@dataclass
class Failed(WithRequest):
    state: ClassVar[ImageState] = ImageState.FAILED


StateData: TypeAlias = Pulled | Prepared | Executing | Succeeded | Failed
StateDataT = TypeVar("StateDataT", bound=StateData)

PREPARATION_STATES = frozenset({ImageState.PREPARING, ImageState.PREPARED})

"""
Permitted state transitions.

Mapping:
    from_state -> allowed to_states
"""
STATE_MACHINE: dict[ImageState, frozenset[ImageState]] = {
    ImageState.PULLED: PREPARATION_STATES,
    ImageState.PREPARING: PREPARATION_STATES,
    ImageState.PREPARED: frozenset({ImageState.PREPARED, ImageState.EXECUTING}),
    ImageState.EXECUTING: frozenset({ImageState.SUCCEEDED, ImageState.FAILED}),
    ImageState.SUCCEEDED: PREPARATION_STATES,
}
