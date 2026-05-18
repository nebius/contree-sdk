from __future__ import annotations

from pathlib import Path

import pytest

from contree_sdk._internals.utils.config import ContreeEndpoint
from contree_sdk.auth import IAMAuth
from tests.unit.auth.ini.helpers import INI_IAM, write_ini


def test_loads_token_and_project_from_ini(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_IAM)
    auth = IAMAuth().resolve()
    assert auth.token == "iam-token-123"
    assert auth.project_id == "proj-abc"
    assert auth.base_url == "https://custom.api.example.com/sandboxes"


def test_env_var_takes_priority_over_ini(ini_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_ini(ini_dir, INI_IAM)
    monkeypatch.setenv("NEBIUS_API_KEY", "env-token")
    auth = IAMAuth().resolve()
    assert auth.token == "env-token"
    assert auth.project_id == "proj-abc"


def test_explicit_value_not_overridden_by_ini(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_IAM)
    auth = IAMAuth(token="explicit-token", project_id="explicit-project").resolve()
    assert auth.token == "explicit-token"
    assert auth.project_id == "explicit-project"


def test_partial_ini_only_fills_missing_fields(ini_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_ini(ini_dir, INI_IAM)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "env-project")
    auth = IAMAuth().resolve()
    assert auth.token == "iam-token-123"
    assert auth.project_id == "env-project"


def test_no_ini_file_keeps_defaults(ini_dir: Path) -> None:
    auth = IAMAuth().resolve()
    assert auth.token == "NEBIUS_API_KEY"
    assert auth.project_id == "NEBIUS_PROJECT_ID"
    assert auth.base_url == ContreeEndpoint.TOKEN_FACTORY_SANDBOXES
