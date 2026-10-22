"""Dockerfile parser and keyword interpreters.

Each Dockerfile directive is a `DockerKeyword` subclass living in its own
module. `parse_dockerfile` returns a list of directives ready to be executed
against a `BuildContext`/`AsyncBuildContext`.
"""

from .asyncio import ContreeAsyncDockerBuilder
from .context import AsyncBuildContext, BuildContext, BuildRequest, BuildStepEvent, PendingFile
from .dockerignore import DockerignoreRule, is_ignored, parse_dockerignore
from .events import BuildEvent, BuildEventType, BuildStep
from .keyword import DockerKeyword, substitute
from .kw_add import AddKeyword
from .kw_arg import ArgKeyword
from .kw_copy import CopyKeyword
from .kw_env import EnvKeyword
from .kw_from import FromKeyword
from .kw_run import RunKeyword
from .kw_skipped import SkippedKeyword
from .kw_user import UserKeyword
from .kw_workdir import WorkdirKeyword
from .local_context import LocalContext
from .parser import DockerfileParser, parse_dockerfile
from .sync import ContreeDockerBuilder


__all__ = [
    "AddKeyword",
    "ArgKeyword",
    "AsyncBuildContext",
    "BuildContext",
    "BuildEvent",
    "BuildEventType",
    "BuildRequest",
    "BuildStep",
    "BuildStepEvent",
    "ContreeAsyncDockerBuilder",
    "ContreeDockerBuilder",
    "CopyKeyword",
    "DockerKeyword",
    "DockerfileParser",
    "DockerignoreRule",
    "EnvKeyword",
    "FromKeyword",
    "LocalContext",
    "PendingFile",
    "RunKeyword",
    "SkippedKeyword",
    "UserKeyword",
    "WorkdirKeyword",
    "is_ignored",
    "parse_dockerfile",
    "parse_dockerignore",
    "substitute",
]
