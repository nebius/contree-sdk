from dataclasses import dataclass

import pytest

from contree_sdk.sdk.exceptions.base import ContreeException


@dataclass()
class MyContreeException(ContreeException):
    field: str


def test_basic_exception():
    with pytest.raises(MyContreeException) as e_info:
        raise MyContreeException(field="foo")
    e = e_info.value

    assert isinstance(e, ContreeException)
    assert e.args == (e.message,)
    assert "MyContreeException" in str(e)
    assert "foo" in str(e)
    assert "field" in str(e)


@dataclass
class MyCustomException(ContreeException):
    field: str
    _template = "Something went wrong with {field}"


def test_basic_custom_exception():
    with pytest.raises(MyCustomException) as e_info:
        raise MyCustomException(field="foo")
    e = e_info.value

    assert isinstance(e, ContreeException)
    assert "Something went wrong with foo" in str(e)
