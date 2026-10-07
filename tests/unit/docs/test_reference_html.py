"""A successful Sphinx build must contain usable Python API objects."""

import subprocess
import sys
import zlib
from html.parser import HTMLParser
from pathlib import Path

import pytest


class ReferencePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.kinds = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "dl":
            self.kinds.update(attributes.get("class", "").split())
        if tag == "a" and "href" in attributes:
            self.links.append(attributes["href"])


@pytest.fixture(scope="module")
def reference_html(tmp_path_factory):
    pytest.importorskip("sphinx")
    pytest.importorskip("myst_parser")
    pytest.importorskip("deepagents")
    root = Path(__file__).resolve().parents[3]
    output = tmp_path_factory.mktemp("reference-html")
    result = subprocess.run(  # noqa: S603 - fixed module and repository-owned documentation
        [sys.executable, "-m", "sphinx", "-b", "html", "-W", "--keep-going", str(root / "docs"), str(output)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output


@pytest.mark.parametrize(
    ("page", "object_name"),
    [
        ("session", "contree_sdk.session.ContreeSession.run"),
        ("execution", "contree_sdk.execution.AsyncExecutor.execute"),
        ("store", "contree_sdk.store.AsyncSQLiteStore.append"),
        ("docker", "contree_sdk.docker.ContreeDockerBuilder.build"),
        ("langchain", "contree_sdk.langchain.ContreeAsyncSandbox.aexecute"),
        ("harbor", "contree_sdk.harbor.runtime.ContreeAsyncRuntime.stop"),
        ("cache", "contree_sdk.cache.SyncMemoryCache.get"),
        ("files", "contree_sdk.files.SyncFileTransfer.read_file"),
        ("exceptions", "contree_sdk.exceptions.SessionConflictError"),
    ],
)
def test_reference_has_linkable_python_objects(reference_html, page, object_name):
    html = (reference_html / "python_sdk" / "reference" / f"{page}.html").read_text()
    parsed = ReferencePage()
    parsed.feed(html)
    assert object_name in parsed.ids
    assert "py" in parsed.kinds
    assert "class" in parsed.kinds or "exception" in parsed.kinds
    if page != "exceptions":
        assert "method" in parsed.kinds
    assert "py:class::" not in html
    assert "py:method::" not in html
    assert not any(link.startswith(("http://Contree", "http://History", "http://Build")) for link in parsed.links)
    inventory = (reference_html / "objects.inv").read_bytes().split(b"\n", 4)[4]
    entries = zlib.decompress(inventory).decode().splitlines()
    assert any(entry.startswith(object_name + " py:") for entry in entries)
