from __future__ import annotations

from pathlib import Path

import pytest

from contree_sdk._internals.utils.auth_ini import read_ini_profile
from tests.unit.auth.ini.conftest import INI_IAM, INI_JWT, INI_MULTI, write_ini


def test_returns_none_when_file_missing(ini_dir: Path) -> None:
    assert read_ini_profile() is None


def test_reads_default_profile(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_IAM)
    profile = read_ini_profile()
    assert profile is not None
    assert profile["token"] == "iam-token-123"
    assert profile["url"] == "https://custom.api.example.com/sandboxes"
    assert profile["project"] == "proj-abc"
    assert profile["type"] == "iam"


def test_reads_named_profile_from_default_section(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_JWT)
    profile = read_ini_profile()
    assert profile is not None
    assert profile["token"] == "jwt-token-456"


def test_reads_explicitly_requested_profile(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_MULTI)
    profile = read_ini_profile(profile="first")
    assert profile is not None
    assert profile["token"] == "token-first"
    assert profile["project"] == "proj-first"


def test_reads_active_profile_from_default_section(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_MULTI)
    profile = read_ini_profile()
    assert profile is not None
    assert profile["token"] == "token-second"


def test_returns_none_for_missing_section(ini_dir: Path) -> None:
    write_ini(ini_dir, INI_IAM)
    assert read_ini_profile(profile="nonexistent") is None


def test_respects_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    monkeypatch.delenv("CONTREE_HOME", raising=False)
    xdg = tmp_path / "xdg"
    contree_dir = xdg / "contree"
    contree_dir.mkdir(parents=True)
    write_ini(contree_dir, INI_IAM)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    profile = read_ini_profile()
    assert profile is not None
    assert profile["token"] == "iam-token-123"


def test_contree_home_takes_priority_over_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_env: None) -> None:
    contree_home = tmp_path / "home"
    contree_home.mkdir()
    write_ini(contree_home, INI_IAM)

    xdg_dir = tmp_path / "xdg" / "contree"
    xdg_dir.mkdir(parents=True)
    write_ini(xdg_dir, INI_JWT)

    monkeypatch.setenv("CONTREE_HOME", str(contree_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    profile = read_ini_profile()
    assert profile is not None
    assert profile["token"] == "iam-token-123"
