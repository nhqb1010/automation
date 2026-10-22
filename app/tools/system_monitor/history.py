"""Short in-memory histories that feed the sparklines."""

import time
from collections import deque
from collections.abc import Callable

DEFAULT_HISTORY_SECONDS = 60.0


class RollingHistory:
    """
    Keeps the samples from the last window of seconds.

    LEARN: the window is measured in time, not in sample count, so the
    sparkline always covers about a minute whether the refresh is 1s or 10s.
    """

    def __init__(
        self,
        window_seconds: float = DEFAULT_HISTORY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = window_seconds
        self._clock = clock
        self._samples: deque[tuple[float, float]] = deque()

    def add_sample(self, value: float) -> None:
        now = self._clock()
        self._samples.append((now, value))
        self._drop_samples_older_than(now - self._window_seconds)

    def values(self) -> list[float]:
        self._drop_samples_older_than(self._clock() - self._window_seconds)
        return [value for _, value in self._samples]

    def _drop_samples_older_than(self, cutoff: float) -> None:
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()


class KeyedRollingHistory:
    """One rolling history per key, used for per-app sparklines."""

    def __init__(
        self,
        window_seconds: float = DEFAULT_HISTORY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = window_seconds
        self._clock = clock
        self._histories: dict[str, RollingHistory] = {}

    def add_sample(self, key: str, value: float) -> None:
        if key not in self._histories:
            self._histories[key] = RollingHistory(
                window_seconds=self._window_seconds, clock=self._clock
            )

        self._histories[key].add_sample(value)

    def values_for(self, key: str) -> list[float]:
        history = self._histories.get(key)
        return history.values() if history else []

    def keep_only_keys(self, keys: set[str]) -> None:
        self._histories = {
            key: history for key, history in self._histories.items() if key in keys
        }
