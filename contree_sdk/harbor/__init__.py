"""Optional Harbor environment backed by ConTree filesystem snapshots."""

import sys


if sys.version_info < (3, 12):  # noqa: RUF067 -- optional integration guard
    raise ImportError("The ConTree Harbor integration requires Python 3.12 or newer.")

try:  # noqa: RUF067 -- actionable optional dependency error
    from contree_sdk.harbor.environment import ConTreeEnvironment
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in {"harbor", "httpx"}:
        raise ImportError("Install the ConTree Harbor integration with: pip install 'contree-sdk[harbor]'") from exc
    raise


__all__ = ["ConTreeEnvironment"]
