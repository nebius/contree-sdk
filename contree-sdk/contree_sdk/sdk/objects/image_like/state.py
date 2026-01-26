from enum import auto

from strenum import StrEnum


# todo use it and use _state_lock inside image like
class ImageState(StrEnum):
    PULLED = auto()  # when pulled from Contree
    PREPARING = auto()  # started to configure run
    PREPARED = auto()  # configured run
    EXECUTING = auto()  # started to execute run

    SUCCEEDED = auto()  # received success result
    FAILED = auto()  # received fail result
