"""Shared state transitions; callers serialize every access."""

from dataclasses import dataclass, field
from typing import Literal

from contree_client.models import OperationEvent


LazyPhase = Literal["cold", "starting", "running", "draining", "snapshotting", "failed", "closed"]


@dataclass
class LazyState:
    phase: LazyPhase = "cold"
    creating: int = 0
    inspecting: int = 0
    active: set[int] = field(default_factory=set)
    early_exits: set[int] = field(default_factory=set)
    error: BaseException | None = None
    closing: bool = False
    snapshots: int = 0
    completion_seen: bool = False
    snapshot_pending: bool = False

    def begin_start(self) -> None:
        self.phase = "starting"
        self.creating = 0
        self.completion_seen = False
        self.snapshot_pending = False
        self.active.clear()
        self.early_exits.clear()

    def finish_start(self) -> None:
        self.phase = "draining" if self.closing or self.snapshot_pending else "running"
        self.snapshot_pending = False

    def reserve(self) -> None:
        self.creating += 1

    def created(self, spid: int) -> None:
        self.creating -= 1
        if spid in self.early_exits:
            self.early_exits.remove(spid)
        else:
            self.active.add(spid)

    def fail(self, error: BaseException) -> None:
        if self.error is None:
            self.error = error
        self.phase = "failed"

    def observe(self, event: OperationEvent | None, error: Exception | None) -> bool:
        if self.phase in {"closed", "failed"}:
            return False
        if error is not None:
            self.fail(error)
        elif event is None:
            if self.phase != "snapshotting" or not self.completion_seen:
                self.fail(RuntimeError("LazySession event stream ended without expected completion"))
        elif event.type == "completion":
            self.completion_seen = True
            if self.phase != "snapshotting":
                self.fail(RuntimeError("LazySession VM ended before a requested snapshot"))
        elif event.type == "exit" and event.spid == 1:
            if self.phase != "snapshotting":
                self.fail(RuntimeError("LazySession main process exited before a requested snapshot"))
        elif event.type == "exit" and isinstance(event.spid, int) and event.spid > 1:
            if event.spid in self.active:
                self.active.remove(event.spid)
                return True
            if self.creating and event.spid not in self.early_exits:
                self.early_exits.add(event.spid)
                return True
        return False

    def request_snapshot(self) -> None:
        if self.phase == "starting":
            self.snapshot_pending = True
        elif self.phase == "running":
            self.phase = "draining"

    def ready_to_snapshot(self) -> bool:
        return self.phase == "draining" and self.creating == 0 and self.inspecting == 0 and not self.active

    def begin_snapshot(self) -> None:
        self.phase = "snapshotting"

    def finish_snapshot(self) -> None:
        self.snapshots += 1
        self.phase = "closed" if self.closing else "cold"

    def request_close(self) -> None:
        self.closing = True
        if self.phase == "cold":
            self.close()
        else:
            self.request_snapshot()

    def close(self) -> None:
        self.closing = True
        self.phase = "closed"

    def ensure_usable(self) -> None:
        if self.error is not None:
            raise RuntimeError(
                "LazySession failed; inspect error and abort before reusing the base session"
            ) from self.error
        if self.closing or self.phase == "closed":
            raise RuntimeError("LazySession is closed")
