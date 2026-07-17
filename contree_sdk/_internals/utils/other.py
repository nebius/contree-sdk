from math import e, log1p
from random import uniform


_JITTER_PEAK_PROGRESS = 0.5
_JITTER_MIN = 0.1
_JITTER_RANGE = 0.4


def get_interval(interval_min: float, interval_max: float, progress: float, steepness: float = 1.0) -> float:
    growth = log1p(progress * (e**steepness - 1)) / steepness
    jitter_size = _JITTER_MIN + _JITTER_RANGE * (1 - 2 * abs(progress - _JITTER_PEAK_PROGRESS))
    growth *= 1 + uniform(-jitter_size, jitter_size)
    result = interval_min + growth * (interval_max - interval_min)
    return max(interval_min, min(result, interval_max))
