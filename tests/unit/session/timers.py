"""Deterministic scheduler injected into snapshot policies."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ManualTimer:
    deadline: float
    callback: Callable[[], None]
    cancelled: bool = False
    fired: bool = False

    def cancel(self) -> None:
        self.cancelled = True


class ManualTimers:
    def __init__(self) -> None:
        self.now = 0.0
        self.timers: list[ManualTimer] = []

    def start(self, seconds: float, callback: Callable[[], None]) -> ManualTimer:
        timer = ManualTimer(self.now + seconds, callback)
        self.timers.append(timer)
        return timer

    def advance(self, seconds: float) -> None:
        self.now += seconds
        for timer in sorted(self.timers, key=lambda item: item.deadline):
            if not timer.cancelled and not timer.fired and timer.deadline <= self.now:
                timer.fired = True
                timer.callback()
