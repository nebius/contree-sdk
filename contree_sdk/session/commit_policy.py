"""Public policies for retaining successful, non-disposable operation results."""

from abc import ABC, abstractmethod

from contree_client.models import InstanceResult

from contree_sdk.execution import OperationContext
from contree_sdk.session.base import exit_code_of


class AbstractCommitPolicy(ABC):
    """Decide whether a validated operation result advances session history.

    Sessions call this synchronous method only after API success, for a
    non-disposable request. Implementations must not perform blocking I/O.
    A policy cannot accept API failure, cancellation, or a missing result image.
    """

    @abstractmethod
    def should_commit(self, context: OperationContext, result: InstanceResult) -> bool: ...


class ApiSuccessCommitPolicy(AbstractCommitPolicy):
    """Retain every successful API result, including a nonzero or unknown exit code."""

    def should_commit(self, context: OperationContext, result: InstanceResult) -> bool:  # noqa: PLR6301 - policy contract
        return True


class ZeroExitCommitPolicy(AbstractCommitPolicy):
    """Retain a result only when its process exit code is explicitly zero."""

    def should_commit(self, context: OperationContext, result: InstanceResult) -> bool:  # noqa: PLR6301 - policy contract
        return exit_code_of(result) == 0
