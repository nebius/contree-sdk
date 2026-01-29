# _internals

Low-level HTTP client layer and other utils. Not part of the public API.

## Structure

- `client/` - HTTP client classes and API endpoints
- `lib/` - `@apied` decorator, request/response handling, async/sync mixins
- `models/` - Response dataclasses for API responses
- `utils/` - AsyncWrapper for sync client support

## Does NOT belong here

- Config (endpoint URLs) → `contree_sdk/config.py`
- Public types → `sdk/` or `utils/`

Everything here is subject to change without notice.
