from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


INI_IAM = textwrap.dedent("""\
    [DEFAULT]
    profile = default

    [profile:default]
    token = iam-token-123
    url = https://custom.api.example.com/sandboxes
    type = iam
    project = proj-abc
""")

INI_JWT = textwrap.dedent("""\
    [DEFAULT]
    profile = myjwt

    [profile:myjwt]
    token = jwt-token-456
    url = https://jwt.api.example.com
    type = jwt
""")

INI_MULTI = textwrap.dedent("""\
    [DEFAULT]
    profile = second

    [profile:first]
    token = token-first
    url = https://first.example.com
    type = iam
    project = proj-first

    [profile:second]
    token = token-second
    url = https://second.example.com
    type = iam
    project = proj-second
""")


_AUTH_ENV_VARS = [
    "NEBIUS_API_KEY",
    "NEBIUS_PROJECT_ID",
    "CONTREE_TOKEN",
    "CONTREE_BASE_URL",
]


def write_ini(directory: Path, content: str) -> Path:
    path = directory / "auth.ini"
    path.write_text(content)
    return path


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _AUTH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def ini_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None) -> Path:
    monkeypatch.setenv("CONTREE_HOME", str(tmp_path))
    return tmp_path
