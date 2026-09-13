"""Fixed-size ring buffer with O(1) running sum and windowed max.

Per #191 (AC1/AC2/AC3): replaces the previous list-based pattern used by
``NATSConsumer.processing_times`` and ``TradeOrderPublisher.publishing_times``:

    values.append(x)
    if len(values) > 1000:
        values = values[-1000:]        # O(n) list realloc, every message
    max_value = max(max_value, x)      # never decays -- lifetime high-water mark
    avg_value = sum(values) / len(values)  # O(n) recompute, every message

``RollingStats`` keeps the exact same window semantics (last ``maxlen``
samples) and produces numerically identical averages, but every operation
below is O(1) amortized: no slice-rebuild, no ``sum()`` over the window, and
the reported max is a true windowed max (a single old spike ages out once it
leaves the window) rather than a lifetime maximum.
"""

from collections import deque


class RollingStats:
    """O(1)-amortized fixed-size window with running sum and running max."""

    __slots__ = ("_maxlen", "_buf", "_sum", "_max_deque")

    def __init__(self, maxlen: int = 1000) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._maxlen = maxlen
        self._buf: deque[float] = deque()
        self._sum: float = 0.0
        # Monotonic (non-increasing) deque of values still eligible to be
        # the max of the current window. Classic "sliding window maximum"
        # structure, keyed by value+FIFO order since `_buf` is itself a
        # strict FIFO queue (no random access removals).
        self._max_deque: deque[float] = deque()

    def add(self, value: float) -> None:
        """Append a new sample, evicting the oldest one if at capacity."""
        if len(self._buf) == self._maxlen:
            evicted = self._buf.popleft()
            self._sum -= evicted
            if self._max_deque and self._max_deque[0] == evicted:
                self._max_deque.popleft()

        self._buf.append(value)
        self._sum += value

        while self._max_deque and self._max_deque[-1] < value:
            self._max_deque.pop()
        self._max_deque.append(value)

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self):
        return iter(self._buf)

    def __getitem__(self, index: int) -> float:
        return self._buf[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RollingStats):
            return list(self._buf) == list(other._buf)
        if isinstance(other, (list, tuple)):
            return list(self._buf) == list(other)
        return NotImplemented

    @property
    def count(self) -> int:
        return len(self._buf)

    @property
    def average(self) -> float:
        if not self._buf:
            return 0.0
        return self._sum / len(self._buf)

    @property
    def windowed_max(self) -> float:
        """Max value currently in the window (0.0 if empty).

        Unlike a lifetime high-water mark, this decays: once the sample
        that set the max ages out of the window, a lower value takes over.
        """
        return self._max_deque[0] if self._max_deque else 0.0
