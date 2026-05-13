from __future__ import annotations

import logging
import os
from abc import abstractmethod
from dataclasses import MISSING, dataclass, fields, replace
from typing import ClassVar

from typing_extensions import Self

from contree_sdk._internals.utils.auth_ini import read_ini_profile
from contree_sdk._internals.utils.config import ContreeEndpoint


logger = logging.getLogger(__name__)


@dataclass
class Auth:
    base_url: str = "CONTREE_BASE_URL"
    """API server URL or env var name to load from."""

    _ini_field_map: ClassVar[dict[str, str]] = {}

    def resolve(self) -> Self:
        ini_profile = read_ini_profile()
        result = self
        for f in fields(self):
            value = getattr(result, f.name)
            if value in os.environ:
                logger.info(f"Loading {f.name} from environment variable {value}")
                result = replace(result, **{f.name: os.environ[value]})
                continue
            if ini_profile is None or f.default is MISSING:
                continue
            if value == f.default:
                ini_key = self._ini_field_map.get(f.name, f.name)
                if ini_value := ini_profile.get(ini_key):
                    logger.info(f"Loading {f.name} from auth.ini")
                    result = replace(result, **{f.name: ini_value})
        return result

    @abstractmethod
    def get_headers(self) -> dict[str, str]: ...


@dataclass
class JWTAuth(Auth):
    token: str = "CONTREE_TOKEN"  # noqa: S105
    """Auth token or env var name to load from."""
    base_url: str = "CONTREE_BASE_URL"
    """API server URL or env var name to load from."""

    _ini_field_map: ClassVar[dict[str, str]] = {"token": "token", "base_url": "url"}

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class IAMAuth(Auth):
    token: str = "NEBIUS_API_KEY"  # noqa: S105
    """IAM token or env var name to load from."""
    project_id: str = "NEBIUS_PROJECT_ID"
    """Nebius project ID or env var name to load from."""
    base_url: str = ContreeEndpoint.TOKEN_FACTORY_SANDBOXES
    """API server URL. Defaults to the Nebius Token Factory production endpoint."""

    _ini_field_map: ClassVar[dict[str, str]] = {"token": "token", "project_id": "project", "base_url": "url"}

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Project": self.project_id}
