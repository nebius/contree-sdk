from pathlib import Path

import pytest
from markdown_pytest import parse_code_blocks


ROOT = Path(__file__).resolve().parents[3]
PAGES = [
    ROOT / "README.md",
    ROOT / "examples/README.md",
    *sorted(p for p in (ROOT / "docs").rglob("*.md") if "_build" not in p.parts),
]


@pytest.mark.parametrize("page", PAGES, ids=lambda page: str(page.relative_to(ROOT)))
def test_every_python_fence_is_collected(page):
    blocks = list(parse_code_blocks(str(page)))
    starts = {block.start_line for block in blocks if block.name.startswith("test")}
    for line_number, line in enumerate(page.read_text().splitlines(), start=1):
        if line.strip() == "```python":
            assert line_number in starts, f"{page}:{line_number}: Python example has no markdown-pytest test"
        assert "{literalinclude}" not in line, f"{page}:{line_number}: executable scenarios must live in Markdown"


def test_reference_sources_are_markdown():
    assert not list((ROOT / "docs").rglob("*.rst"))
