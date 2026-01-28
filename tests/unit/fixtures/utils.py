import re
from re import escape
from typing import Any

from httpx import QueryParams


r = re.compile


def url(path: str, params: dict[str, Any] | None = None) -> re.Pattern:
    if params is not None:
        path += escape("?" + str(QueryParams(params)))
    return r(".*" + path)
