from dataclasses import dataclass

import pytest

from contree_sdk.sdk.exceptions.base import ContreeError


@dataclass()
class MyContreeError(ContreeError):
    field: str


def test_basic_exception():
    with pytest.raises(MyContreeError) as e_info:
        raise MyContreeError(field="foo")
    e = e_info.value

    assert isinstance(e, ContreeError)
    assert e.args == (e.message,)
    assert "MyContreeError" in str(e)
    assert "foo" in str(e)
    assert "field" in str(e)


@dataclass
class MyCustomError(ContreeError):
    field: str
    _template = "Something went wrong with {field}"


def test_basic_custom_exception():
    with pytest.raises(MyCustomError) as e_info:
        raise MyCustomError(field="foo")
    e = e_info.value

    assert isinstance(e, ContreeError)
    assert "Something went wrong with foo" in str(e)
