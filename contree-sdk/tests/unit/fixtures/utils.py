import re
from re import escape

from httpx import QueryParams


r = re.compile


def url(path: str, params: dict | None = None) -> re.Pattern:
    if params is not None:
        path += escape("?" + str(QueryParams(params)))
    return r(".*" + path)
