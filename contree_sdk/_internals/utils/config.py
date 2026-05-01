import importlib.metadata
import logging
import platform
from sys import version_info

from strenum import StrEnum


class ContreeEndpoint(StrEnum):
    PROD_NORTH = "https://eu-north.nebius.computer"
    STAGE_NORTH = "https://eu-north-stage.nebius.computer"
    TOKEN_FACTORY_SANDBOXES = "https://api.tokenfactory.nebius.com/sandboxes/"  # noqa: S105


logger = logging.getLogger(__name__)


PYTHON_VERSION = f"{'.'.join(map(str, version_info))}"

OS_NAME = platform.system()
OS_VERSION = platform.release()

PACKAGE_NAME = "contree-sdk"
try:
    PACKAGE_VERSION = importlib.metadata.version("contree-sdk")
except importlib.metadata.PackageNotFoundError:
    PACKAGE_VERSION = "unknown"


def build_user_agent():
    user_agent = f"{PACKAGE_NAME}/{PACKAGE_VERSION} python/{PYTHON_VERSION} {OS_NAME}/{OS_VERSION}"
    logger.debug(f"User-agent: {user_agent}")

    return user_agent
