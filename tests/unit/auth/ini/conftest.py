from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.auth.ini.helpers import AUTH_ENV_VARS


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in AUTH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def ini_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None) -> Path:
    monkeypatch.setenv("CONTREE_HOME", str(tmp_path))
    return tmp_path
