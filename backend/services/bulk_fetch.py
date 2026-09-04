"""Bounded parallel fan-out for the bulk *window* endpoints (spec
2026-09-05-reading-flow-design R2/R5).

Read-all and whole-series download open a window of chapters at once. Fetched
one after another that is N × (upstream round trip); fetched with no ceiling it
is a burst that gets this egress blocked — Toonily and Bbato already are. This
is the one place that compromise is expressed.

Three things it deliberately does NOT do:

* **It does not fetch.** ``work`` calls the ordinary service path, which
  resolves the shared per-source connector and its pooled, keep-alive
  ``httpx.Client``. There is no second HTTP layer here, and no second retry or
  politeness policy: the connector's own ``min_interval`` (0.21 s, held under a
  lock on the one cached instance per source) still spaces every request to a
  given site, so widening this pool overlaps round trips without hitting the
  source any harder.
* **It does not touch the database.** A SQLAlchemy ``Session`` is not
  thread-safe, and the request's session belongs to the request thread. Callers
  do their DB work — cache reads, the 18+ gate, cache writes — on that thread,
  before and after the fan-out. Passing a ``work`` that reads or writes the
  session is a bug this module cannot catch for you.
* **It does not raise.** One chapter failing upstream must cost that chapter,
  not the window (the whole point of a per-chapter status). Exceptions come back
  in the result list, in position, for the caller to render.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Sequence, TypeVar

from core.config import get_settings
from core.errors import AppError

T = TypeVar("T")
R = TypeVar("R")

#: Upper bound on the pool regardless of configuration — the box has 2 vCPU and
#: these threads each hold an upstream socket.
MAX_CONCURRENCY = 16


def resolved_concurrency(requested: int | None = None) -> int:
    """The effective worker count: ``requested`` (or the configured default),
    clamped to ``[1, MAX_CONCURRENCY]``."""
    value = (
        requested
        if requested is not None
        else getattr(get_settings(), "bulk_fetch_concurrency", 4)
    )
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 4
    return max(1, min(MAX_CONCURRENCY, value))


def map_bounded(
    items: Sequence[T],
    work: Callable[[T], R],
    *,
    concurrency: int | None = None,
) -> list[R | BaseException]:
    """Apply ``work`` to every item with a bounded pool; results stay in order.

    A failure is returned in place as the exception instance rather than raised,
    so a window degrades to a per-item status instead of a 500 for the batch.
    """
    if not items:
        return []
    workers = min(resolved_concurrency(concurrency), len(items))
    if workers <= 1:
        results: list[R | BaseException] = []
        for item in items:
            try:
                results.append(work(item))
            except Exception as exc:  # noqa: BLE001 - reported per item
                results.append(exc)
        return results

    # A per-request pool rather than a process-wide one: a shared pool would
    # make two concurrent readers queue behind each other's whole window, and
    # the inbound `bulk` rate-limit bucket already bounds how many of these
    # requests can be in flight at all.
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="mm-bulk"
    ) as pool:
        futures = [pool.submit(work, item) for item in items]
        out: list[R | BaseException] = []
        for future in futures:
            try:
                out.append(future.result())
            except Exception as exc:  # noqa: BLE001 - reported per item
                out.append(exc)
        return out


#: The per-item failure envelope. Same three fields the top-level error envelope
#: uses (``code`` / ``message``, plus the ``status`` it would have been served
#: as), so a client can reuse its existing ``ApiError`` parsing on a window item.
def item_error(source_id: str, exc: BaseException) -> dict[str, Any]:
    """Render one failed window item, without leaking internals.

    An ``AppError`` already is a client-facing failure and passes through. A raw
    connector failure is mapped through ``BrowseService``'s own translation so
    "Cloudflare blocked us" and "the site timed out" read the same here as they
    do on the single-chapter routes. Anything else collapses to a generic 502 —
    an unexpected exception's text is a server internal and a window item is a
    poor place to publish one.
    """
    if isinstance(exc, AppError):
        return {
            "code": exc.code,
            "status": exc.status_code,
            "message": exc.message,
        }

    from services.browse_service import BrowseService

    try:
        BrowseService._raise_source_connector_error(source_id, exc)  # noqa: SLF001
    except AppError as mapped:
        return {
            "code": mapped.code,
            "status": mapped.status_code,
            "message": mapped.message,
        }
    except BaseException:  # noqa: BLE001 - not a shape it knows; fall through
        pass
    return {
        "code": "chapter_unavailable",
        "status": 502,
        "message": "The source did not return this chapter.",
    }
