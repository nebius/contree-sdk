import re
from re import escape
from typing import Any
from urllib.parse import quote, urlencode


r = re.compile


def url(path: str, params: dict[str, Any] | None = None) -> re.Pattern[str]:
    if params is not None:
        query = urlencode({name: str(value) for name, value in params.items()}, safe="/", quote_via=quote)
        path += escape("?" + query)
    return r(".*" + path)
