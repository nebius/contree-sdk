from datetime import datetime
from typing import Any

from cattrs.preconf.json import make_converter

from contree_sdk._internals.lib.types import ReturnType


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


def args_kwargs_to_kwargs(all_params: list[str], args: tuple, kwargs: dict) -> dict:
    kwargs = kwargs.copy()

    for param, arg in zip(all_params, args, strict=False):
        kwargs[param] = arg
    return kwargs
