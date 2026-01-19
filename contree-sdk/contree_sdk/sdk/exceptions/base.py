from dataclasses import dataclass
from typing import ClassVar


@dataclass
class ContreeError(Exception):
    _template: ClassVar[str | None] = None

    @property
    def message(self) -> str:
        if self._template is None:
            return repr(self)
        return self._template.format(**self.__dict__)

    def __post_init__(self) -> None:
        super().__init__(self.message)
