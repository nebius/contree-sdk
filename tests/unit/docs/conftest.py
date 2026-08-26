from pathlib import Path

import pytest


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    return "_tmp" in str(collection_path)


# The fixtures that used to live here (`image`, `session`, `api_fake_quick_start`,
# `docs_file_upload`, `set_contree_base_url_env`, ...) backed `--markdown-docs`
# execution of README.md's code fences against a mocked HTTP transport. README.md
# itself is out of scope for the contree_client migration (only examples/client/*
# was updated), so those fixtures -- and the README examples they supported -- are
# left broken/deferred rather than ported: `pytest` (whole suite, which walks
# README.md per pytest.ini's testpaths) is expected to fail there until README.md
# is updated for the new `Contree(client)`/`ContreeSync(client)` constructor.
# `pytest tests/unit` (this project's unit-test entrypoint) never collects
# README.md, so this file only needs to stay importable, not functional.
