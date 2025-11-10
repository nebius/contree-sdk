from contree_sdk.client.types import ReturnType


def convert_data_to_type(data: dict | int | str | list, return_type: ReturnType) -> ReturnType:
    from pydantic import TypeAdapter

    return TypeAdapter(return_type).validate_python(data)


def args_kwargs_to_kwargs(all_params, args, kwargs):
    kwargs = kwargs.copy()

    for param, arg in zip(all_params, args, strict=False):
        kwargs[param] = arg
    return kwargs
