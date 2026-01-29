from random import uniform

from contree_sdk.config import ContreeConfig


JITTER_PEAK_PROGRESS = 0.5
JITTER_MIN = 0.1
JITTER_RANGE = 0.4


def get_wait_interval(config: ContreeConfig, progress_ratio: float) -> float:
    progress_ratio **= 1 / config.operation_poll_secs_backoff_grow
    jitter_size = JITTER_MIN + JITTER_RANGE * (1 - 2 * abs(progress_ratio - JITTER_PEAK_PROGRESS))
    progress_ratio *= 1 + uniform(-jitter_size, jitter_size)
    res = config.operation_poll_secs_min + progress_ratio * (
        config.operation_poll_secs_max - config.operation_poll_secs_min
    )
    return max(config.operation_poll_secs_min, min(res, config.operation_poll_secs_max))
