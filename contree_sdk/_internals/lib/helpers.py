from datetime import datetime
from typing import Any, TypeVar

from cattrs.preconf.json import make_converter


ReturnType = TypeVar("ReturnType")


_converter = make_converter()


def _parse_datetime_with_z(value: Any, _type: type) -> datetime:
    """Parse ISO 8601 datetime with Z suffix support for Python 3.10.

    Args:
        value: String representation of datetime or datetime object.
        _type: Target type (datetime).

    Returns:
        Parsed datetime object.

    """
    if isinstance(value, str):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


_converter.register_structure_hook(datetime, _parse_datetime_with_z)


def convert_data_to_type(data: dict | int | str | list, return_type: type[ReturnType]) -> ReturnType:
    return _converter.structure(data, return_type)
