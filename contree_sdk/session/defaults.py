"""Lifecycle defaults shared by synchronous and asynchronous sessions."""

DEFAULT_READINESS_TIMEOUT = 30.0
READINESS_RETRY_INTERVAL = 0.2
DEFAULT_SHUTDOWN_TIMEOUT = 10.0
DEFAULT_SNAPSHOT_TIMEOUT = 30
DEFAULT_IDLE_SNAPSHOT_SECONDS = 10

# The VM timeout controls lifetime; sleep keeps its main process alive until then.
KEEPALIVE_SLEEP_SECONDS = 2**31 - 1
