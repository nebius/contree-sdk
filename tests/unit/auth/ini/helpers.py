from __future__ import annotations

import textwrap
from pathlib import Path


INI_IAM = textwrap.dedent("""\
    [DEFAULT]
    profile = default

    [profile:default]
    token = iam-token-123
    url = https://custom.api.example.com/sandboxes
    type = iam
    project = proj-abc
""")

INI_JWT = textwrap.dedent("""\
    [DEFAULT]
    profile = myjwt

    [profile:myjwt]
    token = jwt-token-456
    url = https://jwt.api.example.com
    type = jwt
""")

INI_MULTI = textwrap.dedent("""\
    [DEFAULT]
    profile = second

    [profile:first]
    token = token-first
    url = https://first.example.com
    type = iam
    project = proj-first

    [profile:second]
    token = token-second
    url = https://second.example.com
    type = iam
    project = proj-second
""")

AUTH_ENV_VARS = [
    "NEBIUS_API_KEY",
    "NEBIUS_PROJECT_ID",
    "CONTREE_TOKEN",
    "CONTREE_BASE_URL",
]


def write_ini(directory: Path, content: str) -> Path:
    path = directory / "auth.ini"
    path.write_text(content)
    return path
