from pathlib import Path

import pytest

from tests import data


@pytest.fixture(scope="session")
def test_data_path() -> Path:
    return Path(data.__file__).parent


@pytest.fixture(scope="session")
def test_txt_path(test_data_path: Path) -> Path:
    return test_data_path / "example.txt"
