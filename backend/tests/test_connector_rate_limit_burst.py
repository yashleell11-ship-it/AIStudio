"""The rate limiter must not cancel a connector's deliberate fan-out.

``SyncConnectorHttpClient`` spaces requests out to be polite. It used to do so
with a hard gap enforced while HOLDING the lock, which meant a connector that
fetches several documents on a ThreadPoolExecutor got no parallelism at all:
its six threads queued behind one another 0.21s apart. Measured from the VPS,
webtoons' chapter stage spent roughly 2.3s of its 3.75s waiting in the limiter
rather than on the network.

It is now a token bucket. The property that must survive is the politeness
budget: a burst may go out together, but the LONG-RUN rate is still one
request per ``min_interval``. Both halves are pinned here — the burst, and the
average it is not allowed to exceed.
"""

from __future__ import annotations

import threading
import time

from connectors.http.client import SyncConnectorHttpClient


def _client(**kwargs) -> SyncConnectorHttpClient:
    client = SyncConnectorHttpClient("https://example.test", **kwargs)
    client.close()  # no network in these tests; only _rate_limit is exercised
    return client


def test_default_client_still_spaces_requests_out() -> None:
    """burst=1 is every existing connector, and must behave as before."""
    client = _client(min_interval=0.05)
    started = time.monotonic()
    for _ in range(4):
        client._rate_limit()
    elapsed = time.monotonic() - started
    # First token is free; the next three each wait one interval.
    assert elapsed >= 0.14, elapsed


def test_a_burst_client_lets_the_batch_leave_together() -> None:
    client = _client(min_interval=0.2, burst=6)
    started = time.monotonic()
    for _ in range(6):
        client._rate_limit()
    assert time.monotonic() - started < 0.05


def test_a_burst_does_not_raise_the_long_run_rate() -> None:
    """Six at once, then the seventh waits — the average is still 1/interval."""
    client = _client(min_interval=0.1, burst=6)
    for _ in range(6):
        client._rate_limit()
    started = time.monotonic()
    client._rate_limit()
    assert time.monotonic() - started >= 0.09


def test_parallel_callers_are_not_serialized_by_each_others_sleeps() -> None:
    """The fan-out case, with real threads.

    Six threads through a burst-6 client should all be through in well under
    the 5 x interval the old gap-based limiter forced on them.
    """
    client = _client(min_interval=0.2, burst=6)
    done = threading.Barrier(7, timeout=10)

    def worker() -> None:
        client._rate_limit()
        done.wait()

    started = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    done.wait()
    elapsed = time.monotonic() - started
    for t in threads:
        t.join(timeout=5)
    assert elapsed < 0.3, elapsed


def test_a_zero_interval_client_never_sleeps() -> None:
    client = _client(min_interval=0.0)
    started = time.monotonic()
    for _ in range(50):
        client._rate_limit()
    assert time.monotonic() - started < 0.05


def test_webtoons_burst_matches_its_fan_out_width() -> None:
    """The setting is only useful if it matches the executor it exists for."""
    from connectors.webtoons.connector import _CHAPTER_PAGE_WORKERS
    from connectors.registry import create_connector

    connector = create_connector("webtoons")
    assert connector._http._burst == _CHAPTER_PAGE_WORKERS
