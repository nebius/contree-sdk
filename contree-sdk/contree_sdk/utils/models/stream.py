from dataclasses import dataclass
from enum import auto

from strenum import LowercaseStrEnum


class StreamEncoding(LowercaseStrEnum):
    base64 = auto()
    ascii = auto()


@dataclass
class StreamDescription:
    value: str
    encoding: StreamEncoding | str = StreamEncoding.base64
    truncated: bool = False
