import sys
from dataclasses import replace

import pytest
from pytest_markdown_docs.plugin import MarkdownInlinePythonItem


pytest_plugins = ["tests.unit.docs.conftest"]

pytestmark = pytest.mark.markdown

_NAME_PREFIX = "name:"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]):
    for item in items:
        if isinstance(item, MarkdownInlinePythonItem):
            if sys.platform == "win32":  # skip only md tests
                item.add_marker(pytest.mark.xfail(reason="may fail on Windows", strict=False))
            fixtures = set(item.fixturenames)

            for fix in list(fixtures):
                if fix.startswith(_NAME_PREFIX):
                    new_name = fix.replace(_NAME_PREFIX, "")
                    item._nodeid = item.nodeid.replace(item.nodeid.split("::")[-1], new_name)
                    item.name = new_name
                    fixtures.remove(fix)

            fixtures = list(fixtures)
            item.test_definition = replace(item.test_definition, fixture_names=fixtures)
            item.fixturenames = fixtures
