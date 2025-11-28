from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from contree_sdk.sdk.exceptions.base import ContreeException
from contree_sdk.sdk.objects.image_like.state import ImageState


@dataclass
class ContreeImageNotFound(ContreeException):
    image_ref: UUID | str | None
    field: Literal["uuid", "tag"] = "uuid"

    _template = 'Image {field} "{image_ref}" not found'


class ContreeImageParametersError(ContreeException): ...


@dataclass
class DisposableImageRunError(ContreeException):
    _template = "Disposable image run cannot be used for running"


@dataclass
class ContreeImageStateError(ContreeException):
    image_uuid: UUID | None
    state: ImageState | str | None
    states: list[ImageState] | None

    @property
    def message(self) -> str:
        res = f'Image state "{self.image_uuid}" cannot have state {self.state}'
        if self.states:
            res += f", it only can be in {self.states}"
        return res


@dataclass
class ContreeImageImpossibleStateError(ContreeImageStateError):
    possible_states: list[ImageState] | None


class ContreeImageEmptyRequestError(ContreeException): ...
