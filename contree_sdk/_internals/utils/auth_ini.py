from __future__ import annotations

import configparser
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from contree_sdk._internals.lib.helpers import convert_data_to_type


logger = logging.getLogger(__name__)


@dataclass
class IniProfile:
    token: str | None = None
    url: str | None = None
    type: str | None = None
    project: str | None = None


def _config_dir() -> Path:
    if home := os.environ.get("CONTREE_HOME"):
        return Path(home)
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "contree"


def _auth_ini_path() -> Path:
    return _config_dir() / "auth.ini"


def read_ini_profile(profile: str | None = None) -> IniProfile | None:
    path = _auth_ini_path()
    if not path.is_file():
        return None
    cp = configparser.ConfigParser()
    try:
        cp.read(path)
    except (OSError, configparser.Error):
        logger.warning("Failed to read %s", path, exc_info=True)
        return None
    active = profile or os.environ.get("CONTREE_PROFILE") or cp.defaults().get("profile", "default")
    section = f"profile:{active}"
    if not cp.has_section(section):
        logger.debug("Profile %s not found in %s", section, path)
        return None
    logger.debug("Loading auth from %s profile %s", path, active)
    return convert_data_to_type(dict(cp[section]), IniProfile)
