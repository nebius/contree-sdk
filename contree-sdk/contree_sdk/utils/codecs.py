from collections.abc import Callable
from functools import partial


def _decode_base64(value: str) -> str:
    import base64

    return base64.b64decode(value).decode("utf-8")


_SPECIAL_DECODERS: dict[str, Callable[[str], str]] = {
    "base64": _decode_base64,
    "ascii": str,
}


def _fallback_decoder(value: str, encoding: str) -> str:
    return value.encode("latin-1").decode(encoding)


def io_decode(value: str, encoding: str, truncated: bool) -> str:
    # todo use truncated
    encoding = encoding.lower()
    decoder = _SPECIAL_DECODERS.get(encoding, partial(_fallback_decoder, encoding=encoding))
    return decoder(value)
