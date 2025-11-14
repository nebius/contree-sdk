import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    marker = pytest.mark.e2e
    for item in items:
        if should_be_marked_e2e.__name__ not in item.fixturenames:
            continue
        item.add_marker(marker)


@pytest.fixture(autouse=True)
def should_be_marked_e2e(): ...
