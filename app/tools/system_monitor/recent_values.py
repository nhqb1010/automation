# LEARN: YOU ARE HERE
#   CPU / RAM / temperature / top apps readers ▶ THIS FILE ▶ recent numbers
#   ▶ sent to the page ▶ drawn as sparklines (the small line charts)
#   read next → app/tools/system_monitor/temperature.py
"""Short in-memory lists of recent values that feed the sparklines."""

# LEARN: import = load code from another module so this file can use it
#   time → clocks
#   deque → a list-like container (explained below)
#   Callable → a type hint meaning "something you can call, like a function"
import time
from collections import deque
from collections.abc import Callable

# LEARN: UPPER_CASE name = a constant (a value meant never to change)
#   60.0 → keep about one minute of values
DEFAULT_WINDOW_SECONDS = 60.0


class RecentValues:
    """
    LEARN: keeps the last 60 s of ONE number (e.g. CPU %)

    called by → the CPU / RAM reader and the temperature reader, every refresh
    gives back → a plain list of numbers ▶ sent to the page ▶ sparkline

    industry term: "rolling window" = only the last N seconds are kept,
    the window slides forward as time passes

      time ─────────────────────────────────────▶
      [ older ✗ dropped ][ last 60 s ✓ kept ]

    measured in seconds, not in number of values
      → the chart always shows ~1 minute, whether refresh is 1 s or 10 s
    """

    # LEARN: class = a blueprint; RecentValues() makes one object from it
    #   each object keeps its own data (its own list of numbers)
    #
    # LEARN: __init__ = runs once, when the object is made
    #   self = "this object"; self.x = ... stores x ON the object
    #
    # LEARN: "name: type = default" in the brackets
    #   window_seconds: float = 60.0 → a decimal number; 60.0 if not given
    #   -> None → this function gives nothing back
    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # LEARN: leading _ = "private" → only used inside this class
        #   (a naming convention; Python does not enforce it)
        self._window_seconds = window_seconds

        # LEARN: the clock is passed in, not hard-coded
        #   app   → real clock (time.monotonic)
        #   tests → a fake clock they move by hand ✓ no real waiting
        #   industry term: "dependency injection"
        #
        # LEARN: monotonic clock = only ever moves forward
        #   ✓ unaffected if the Mac's time is changed
        #   Callable[[], float] = takes nothing, returns a decimal number
        self._clock = clock

        # LEARN: deque = list with fast add / remove at BOTH ends
        #   list.pop(0)      → shifts every item ✗ slow
        #   deque.popleft()  → instant ✓
        #
        # each item = a pair (tuple): (time it was taken, the value)
        #   deque[tuple[float, float]] = "a deque of (decimal, decimal) pairs"
        self._samples: deque[tuple[float, float]] = deque()

    def add_sample(self, value: float) -> None:
        """
        LEARN: remember one new value, stamped with the current time

        called by → the readers, once per refresh
        """
        now = self._clock()
        self._samples.append((now, value))
        self._drop_samples_older_than(now - self._window_seconds)

    def values(self) -> list[float]:
        """
        LEARN: the kept values, oldest first, times left out

        called by → the readers, to put the list into what goes to the page
        """
        self._drop_samples_older_than(self._clock() - self._window_seconds)

        # LEARN: list comprehension = a for-loop that builds a list, in one line
        #   same as:
        #     result = []
        #     for (taken_at, value) in self._samples:
        #         result.append(value)
        #   _ = "a value I don't need" (here: the time)
        return [value for _, value in self._samples]

    def _drop_samples_older_than(self, cutoff: float) -> None:
        # LEARN: values are stored oldest → newest
        #   so: keep removing from the front while the front one is too old
        #   self._samples[0]    = the oldest pair
        #   self._samples[0][0] = its time
        #   "while self._samples and ..." → stop when empty (no crash on [0])
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()


class RecentValuesPerApp:
    """
    LEARN: one RecentValues list per app

    called by → the top apps reader, every refresh while a list is open
    gives back → each app's own recent values ▶ that app row's sparkline

    ≈ dict[app → last 60 s of values]

      "Google Chrome" → [12, 15, 30, 22 …]
      "Slack"         → [ 3,  4,  2 …]
    """

    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = window_seconds
        self._clock = clock
        # LEARN: dict[str, RecentValues] = keys are app ids (text),
        #   values are RecentValues objects; starts empty ({})
        self._values_by_app: dict[str, RecentValues] = {}

    def add_sample(self, app_key: str, value: float) -> None:
        # first value for this app → make its list first
        if app_key not in self._values_by_app:
            self._values_by_app[app_key] = RecentValues(
                window_seconds=self._window_seconds, clock=self._clock
            )

        self._values_by_app[app_key].add_sample(value)

    def values_for(self, app_key: str) -> list[float]:
        # LEARN: dict.get(key) → the value, or None when the key is missing
        #   (dict[key] would crash instead)
        recent = self._values_by_app.get(app_key)

        # LEARN: "a if condition else b" = one-line if / else
        #   same as: if recent: return recent.values() / else: return []
        return recent.values() if recent else []

    def keep_only_apps(self, app_keys: set[str]) -> None:
        """
        LEARN: forget apps that left the top list

        ✗ without this → memory grows with every app ever seen

        set[str] = a collection of unique texts, fast "is x in it?" checks
        """
        # LEARN: dict comprehension = like a list comprehension, builds a dict
        #   same as:
        #     kept = {}
        #     for key, recent in self._values_by_app.items():
        #         if key in app_keys:
        #             kept[key] = recent
        #   .items() → each (key, value) pair of the dict
        self._values_by_app = {
            key: recent
            for key, recent in self._values_by_app.items()
            if key in app_keys
        }
