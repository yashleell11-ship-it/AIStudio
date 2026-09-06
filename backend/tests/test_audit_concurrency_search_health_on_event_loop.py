"""AUDIT (concurrency): federated search commits to SQLite on the event loop.

``GET /sources/search`` is an ``async def`` route (routes/sources.py:135) and
``BrowseService.federated_search`` calls ``_merge_health`` inline
(browse_service.py:875), which runs ``load_states`` (a SELECT) and
``record_outcomes`` (a COMMIT, source_health.py:305) on the request's sync
Session — on the event-loop thread. A commit that has to wait for SQLite's
write lock (busy_timeout is 5 s) stalls every other request in the process,
not just this one.

Expected: the health read/write never executes on a thread that has a running
event loop.
"""

from __future__ import annotations

import asyncio

import services.browse_service as browse_service
from services.browse_service import BrowseService


def test_health_recording_runs_off_the_event_loop(db_session, monkeypatch):
    seen: dict[str, bool] = {}

    def fake_record_outcomes(db, results, *, now=None):  # noqa: ARG001
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return {}

    monkeypatch.setattr(browse_service, "record_outcomes", fake_record_outcomes)

    async def fake_fan_out(self, query, source_ids, *, page):  # noqa: ARG001
        return {sid: TimeoutError("Search deadline exceeded.") for sid in source_ids}

    monkeypatch.setattr(BrowseService, "_fan_out_search", fake_fan_out)

    service = BrowseService(mature_enabled=False, db=db_session)
    asyncio.run(service.federated_search("naruto", include_mature=False))

    assert seen, "record_outcomes was not reached"
    assert seen["on_loop"] is False, "source_health commit ran on the event-loop thread"
