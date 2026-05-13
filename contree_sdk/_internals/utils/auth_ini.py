from __future__ import annotations

import configparser
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)


def _config_dir() -> Path:
    if home := os.environ.get("CONTREE_HOME"):
        return Path(home)
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "contree"


def _auth_ini_path() -> Path:
    return _config_dir() / "auth.ini"


def read_ini_profile(profile: str | None = None) -> dict[str, str] | None:
    path = _auth_ini_path()
    if not path.exists():
        return None
    cp = configparser.ConfigParser()
    cp.read(path)
    active = profile or os.environ.get("CONTREE_PROFILE") or cp.defaults().get("profile", "default")
    section = f"profile:{active}"
    if not cp.has_section(section):
        logger.debug("Profile %s not found in %s", section, path)
        return None
    logger.debug("Loading auth from %s profile %s", path, active)
    return dict(cp[section])
