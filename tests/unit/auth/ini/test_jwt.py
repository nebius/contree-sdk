from __future__ import annotations

from pathlib import Path

import pytest

from contree_sdk.auth import JWTAuth
from tests.unit.auth.ini.conftest import INI_JWT, write_ini


def test_loads_token_and_url_from_ini(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_JWT)
    auth = JWTAuth().resolve()
    assert auth.token == "jwt-token-456"
    assert auth.base_url == "https://jwt.api.example.com"


def test_env_var_takes_priority_over_ini(ini_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_ini(ini_dir, INI_JWT)
    monkeypatch.setenv("CONTREE_TOKEN", "env-jwt-token")
    auth = JWTAuth().resolve()
    assert auth.token == "env-jwt-token"
    assert auth.base_url == "https://jwt.api.example.com"


def test_explicit_value_not_overridden_by_ini(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_JWT)
    auth = JWTAuth(token="my-explicit-token").resolve()
    assert auth.token == "my-explicit-token"
