"""Unit tests for rate_limit.py, with a fake clock instead of real waiting."""
from rate_limit import SlidingWindowLimiter


class FakeClock:
    """Stands in for time.monotonic; tests move time by setting .now."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_eleventh_request_in_a_minute_is_refused():
    limiter = SlidingWindowLimiter(limit=10, window=60, clock=FakeClock())
    results = [limiter.allow("user:a") for _ in range(11)]
    assert results == [True] * 10 + [False]


def test_each_caller_has_its_own_count():
    limiter = SlidingWindowLimiter(limit=1, window=60, clock=FakeClock())
    assert limiter.allow("user:a")
    assert not limiter.allow("user:a")
    assert limiter.allow("user:b")


def test_window_slides_instead_of_resetting():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=2, window=60, clock=clock)
    assert limiter.allow("k")  # t=0
    clock.now = 30
    assert limiter.allow("k")  # t=30, now full
    assert not limiter.allow("k")
    clock.now = 59.9
    assert not limiter.allow("k")  # the t=0 request still counts
    clock.now = 60
    assert limiter.allow("k")  # t=0 dropped out; t=30 still counts
    assert not limiter.allow("k")
