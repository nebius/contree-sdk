from collections.abc import Callable

import pytest


def create_directory_marker(marker: pytest.MarkDecorator) -> tuple[Callable, Callable]:
    fixture_name: str = f"should_be_marked_{marker.name}"

    def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
        for item in items:
            if not isinstance(item, pytest.Function):
                continue
            if fixture_name not in item.fixturenames:
                continue
            item.add_marker(marker)

    def autouse_fixture(): ...

    autouse_fixture.__name__ = fixture_name
    autouse_fixture = pytest.fixture(autouse=True)(autouse_fixture)

    return pytest_collection_modifyitems, autouse_fixture
