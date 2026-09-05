"""The per-caller 18+ gate on ``source_series_cache`` reads (spec §3.10, §5.2).

``source_series_cache`` rows are GLOBAL, exactly like the browse-page and cover
rows beside them, so whether a caller may see the source has to be decided per
request. ``get_browse_page`` and ``get_series_cover`` always decided it;
``get_series_meta`` decided it only by accident and only sometimes — a miss went
through ``BrowseService.get_series``, which resolves the connector and so gated,
while a fresh hit answered off the global row without asking. On a miss the
gate's own 404 is an ``AppError``, which the degrade-to-stale handler then
caught and served the row anyway.

Nothing leaked: every caller (reader manifest, novels, followed detail) gates
before it gets here. These tests pin the gate to the entry point instead of to
the cache state, so the next caller added inherits it.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from core.errors import AppError
from core.time_utils import utcnow
from database.models import SourceSeriesCache
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse

MATURE_SRC = "toonily"
SAFE_SRC = "mangadex"
KEY = "some-series"

_FIXTURE = {
    (MATURE_SRC, KEY): {
        "meta": {"title": "Live Title"},
        "chapters": [{"id": "c1", "number": 1.0, "title": "Ch 1"}],
    },
    (SAFE_SRC, KEY): {
        "meta": {"title": "Live Title"},
        "chapters": [{"id": "c1", "number": 1.0, "title": "Ch 1"}],
    },
}


def _gated_browse() -> FakeBrowse:
    """A caller whose 18+ gate is CLOSED, looking at a mature source."""
    browse = FakeBrowse(_FIXTURE)
    browse.mature_sources = {MATURE_SRC}
    browse.gate_open = False
    return browse


def _seed_row(db, *, source_id: str = MATURE_SRC, age_hours: float = 1.0):
    row = SourceSeriesCache(
        source_id=source_id,
        series_key=KEY,
        title="Cached Title",
        fetched_at=utcnow() - timedelta(hours=age_hours),
        chapters='[{"id": "c1", "number": 1.0, "title": "Ch 1"}]',
    )
    db.add(row)
    db.commit()
    return row


def test_fresh_row_for_a_mature_source_is_not_served_to_a_closed_gate(db_session):
    """The case the cache-state dependency actually hid: a row young enough to
    be a fresh hit never reached the connector, and so never met the gate."""
    _seed_row(db_session, age_hours=1)  # TTL is 6h
    browse = _gated_browse()

    with pytest.raises(AppError) as exc:
        SourceCacheService(db_session, browse).get_series_meta(MATURE_SRC, KEY)

    assert exc.value.status_code == 404
    assert exc.value.code == "source_not_found"
    assert browse.calls == []  # gated without touching the connector


def test_stale_row_is_not_served_when_the_connector_is_down(db_session):
    """The sharper half. On a miss the gate raises ``AppError`` — and the
    degrade-to-stale handler catches ``AppError``, so before the gate moved to
    the top of the method a closed gate on an expired row was answered with the
    row. Serving stale must degrade availability, never authorisation."""
    _seed_row(db_session, age_hours=10)  # past the 6h TTL
    browse = _gated_browse()
    browse.down = True

    with pytest.raises(AppError) as exc:
        SourceCacheService(db_session, browse).get_series_meta(MATURE_SRC, KEY)

    assert exc.value.status_code == 404


def test_a_miss_is_gated_before_the_connector_is_asked(db_session):
    """Nothing cached at all: the gate still answers first, so a gated caller
    cannot use response latency (or an upstream failure) as an oracle."""
    browse = _gated_browse()

    with pytest.raises(AppError):
        SourceCacheService(db_session, browse).get_series_meta(MATURE_SRC, KEY)

    assert browse.calls == []


def test_chapter_list_inherits_the_gate(db_session):
    """``get_chapter_list`` is a projection of ``get_series_meta``; the reader
    and the novel adjacency index both read the cache through it."""
    _seed_row(db_session, age_hours=1)
    browse = _gated_browse()

    with pytest.raises(AppError) as exc:
        SourceCacheService(db_session, browse).get_chapter_list(MATURE_SRC, KEY)

    assert exc.value.status_code == 404


def test_the_gate_is_the_callers_own_not_a_blanket_block(db_session):
    """Same source, same global row, gate OPEN — served. The gate is a property
    of the (user, profile) the ``BrowseService`` was built for, which is why it
    is asked rather than read from settings here."""
    _seed_row(db_session, age_hours=1)
    browse = FakeBrowse(_FIXTURE)
    browse.mature_sources = {MATURE_SRC}
    browse.gate_open = True

    meta = SourceCacheService(db_session, browse).get_series_meta(MATURE_SRC, KEY)

    assert meta["title"] == "Cached Title"


def test_a_general_source_reads_exactly_as_before(db_session):
    """The gate must not cost the ordinary path anything: a non-mature source
    with the gate closed still serves its fresh row without a connector call."""
    _seed_row(db_session, source_id=SAFE_SRC, age_hours=1)
    browse = _gated_browse()

    meta = SourceCacheService(db_session, browse).get_series_meta(SAFE_SRC, KEY)

    assert meta["title"] == "Cached Title"
    assert browse.calls == []


def test_series_meta_denies_exactly_as_browse_does(db_session):
    """One rule, one answer. A gated caller must not be able to tell the series
    cache from the browse cache — same code, same status, same message — or the
    difference itself discloses which sources are installed."""
    _seed_row(db_session, age_hours=1)
    svc = SourceCacheService(db_session, _gated_browse())

    with pytest.raises(AppError) as from_browse:
        svc.get_browse_page(MATURE_SRC)
    with pytest.raises(AppError) as from_meta:
        svc.get_series_meta(MATURE_SRC, KEY)

    assert (from_meta.value.code, from_meta.value.status_code) == (
        from_browse.value.code,
        from_browse.value.status_code,
    )
    assert str(from_meta.value) == str(from_browse.value)
