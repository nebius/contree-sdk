import pytest

from tests.utils.marker import create_directory_marker


pytest_collection_modifyitems, should_be_marked_e2e = create_directory_marker(pytest.mark.e2e)
