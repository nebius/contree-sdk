from dataclasses import replace

import pytest
from pytest import Config, Item
from pytest_markdown_docs.plugin import MarkdownInlinePythonItem


pytest_plugins = ["tests.unit.docs.conftest"]

pytestmark = pytest.mark.markdown

_NAME_PREFIX = "name:"


def pytest_collection_modifyitems(config: Config, items: list[Item]):
    for item in items:
        if isinstance(item, MarkdownInlinePythonItem):
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
