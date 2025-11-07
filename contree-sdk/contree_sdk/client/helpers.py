from contree_sdk.client.types import ReturnType


def convert_data_to_type(data: dict | int | str | list, return_type: ReturnType) -> ReturnType:
    from pydantic import TypeAdapter

    return TypeAdapter(return_type).validate_python(data)
