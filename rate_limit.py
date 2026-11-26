"""
Phase 4 sliding-window rate limiter, kept in memory.

Pure Python (no FastAPI), like audit.py and auth.py, so it's easy to
unit-test with a fake clock instead of waiting a real minute.
"""
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Allow at most `limit` requests per `window` seconds for each key.

    Each key keeps the times of its recent allowed requests. Before each
    decision, times older than the window are dropped, so the window
    "slides" with the clock instead of resetting at fixed minute marks.
    """

    def __init__(self, limit: int, window: float, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self.clock()
        hits = self.hits[key]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
        