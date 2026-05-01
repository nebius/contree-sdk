from __future__ import annotations

import logging
import os
from abc import abstractmethod
from dataclasses import dataclass, fields, replace

from typing_extensions import Self

from contree_sdk._internals.utils.config import ContreeEndpoint


logger = logging.getLogger(__name__)


@dataclass
class Auth:
    base_url: str = "CONTREE_BASE_URL"
    """API server URL or env var name to load from."""

    def resolve(self) -> Self:
        result = self
        for f in fields(self):
            value = getattr(result, f.name)
            if value in os.environ:
                logger.info(f"Loading {f.name} from environment variable {value}")
                result = replace(result, **{f.name: os.environ[value]})
        return result

    @abstractmethod
    def get_headers(self) -> dict[str, str]: ...


@dataclass
class JWTAuth(Auth):
    token: str = "CONTREE_TOKEN"  # noqa: S105
    """Auth token or env var name to load from."""
    base_url: str = "CONTREE_BASE_URL"
    """API server URL or env var name to load from."""

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

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Project": self.project_id}
