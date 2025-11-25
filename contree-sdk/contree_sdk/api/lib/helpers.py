from cattrs.preconf.json import make_converter

from contree_sdk.api.lib.types import ReturnType


_converter = make_converter()


def convert_data_to_type(data: dict | int | str | list, return_type: type[ReturnType]) -> ReturnType:
    return _converter.structure(data, return_type)


def args_kwargs_to_kwargs(all_params, args, kwargs):
    kwargs = kwargs.copy()

    for param, arg in zip(all_params, args, strict=False):
        kwargs[param] = arg
    return kwargs
