"""The reader's OWN 18+ gate, pinned independently of the cache beneath it.

``ReaderService.manifest`` and ``manifest_batch`` each open with
``BrowseService.ensure_visible``, and every existing test of those two gates
passes with that line deleted. Not because the gate does not matter — because
it is *masked*: the very next statement resolves the chapter list through
``SourceCacheService.get_series_meta``, which runs its own ``ensure_visible``
first (pinned by ``test_source_cache_gate.py``), so a gated caller is refused
either way and no assertion downstream of the call can tell which line refused
it. Deleting both reader guards kills zero tests.

Masking is not redundancy, for two reasons.

*The downstream gate is young.* ``get_series_meta`` gated only on a cache MISS
until recently: a fresh hit answered off the global row without asking, and on
a miss the gate's own ``AppError`` was swallowed by the degrade-to-stale
handler. That is the regression this file's construction simulates, and the
reader's guard is what makes ``manifest`` correct on its own terms instead of
by a collaborator's current internals.

*In the bulk path the reader's guard outranks the connector's.* The other gate
on this path rides on connector resolution inside ``get_chapter_pages`` — but
``manifest_batch`` degrades per chapter, so a key the resolved list does not
contain becomes a ``chapter_not_found`` item and never reaches that call at
all. Lose the cache's gate and the reader's together and such a window answers
HTTP 200 with a per-item error announcing the mature source is installed and
cached, which is the exact bit a shut gate exists to withhold. Whole-window
denial is the invariant, and the reader's own line is what produces it.

The masking is broken here by handing the reader a cache whose gate is already
satisfied: the reader's own ``BrowseService`` is shut for the source, the one
behind its ``SourceCacheService`` is open. That pairing cannot occur in
production — ``ReaderService.__init__`` builds the cache from its own browse —
which is the point: it is the shape of the failure, the one construction in
which the reader's line is the only thing that can refuse.
"""

from __future__ import annotations

import pytest

from core.errors import AppError
from services.reader_service import ReaderService
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse

SRC = "toonily"
SERIES = "a-mature-series"


def _fixture() -> dict:
    """A FRESH fixture per call — ``FakeBrowse`` keeps the dict it is handed."""
    return {
        (SRC, SERIES): {
            "meta": {"title": "Gated"},
            "chapters": [
                {"id": "ch-1", "number": 1.0, "title": "One"},
                {"id": "ch-2", "number": 2.0, "title": "Two"},
            ],
            "pages": {
                "ch-1": [{"number": 1, "image_url": "/a"}],
                "ch-2": [{"number": 1, "image_url": "/b"}],
            },
        }
    }


def _split_gate_reader(
    db, *, reader_gate_open: bool
) -> tuple[ReaderService, FakeBrowse, FakeBrowse]:
    """A reader whose own gate differs from the one its cache answers to.

    Two ``FakeBrowse`` instances over the same fixture: the reader holds
    ``own``, ``SourceCacheService`` holds ``below``, and only ``own`` knows the
    source is mature. Reaching past ``__init__`` to swap the cache's browse is
    the whole construction — built normally the two are one object, and that
    identity is what hides which layer refused.
    """
    own = FakeBrowse(_fixture())
    own.mature_sources = {SRC}
    own.gate_open = reader_gate_open

    # No ``mature_sources``, so ``ensure_visible`` here always passes: a stand-in
    # for the layer below having stopped gating.
    below = FakeBrowse(_fixture())

    svc = ReaderService(own, db=db)
    svc._cache = SourceCacheService(db, below)
    return svc, own, below


def test_single_manifest_refuses_on_its_own_line(db_session):
    """``manifest`` must 404 from its own guard, not from the cache's.

    With the cache below it answering freely, the reader's ``ensure_visible``
    is the only remaining refusal — and it has to happen before the chapter
    list is resolved, or the page list is fetched, on behalf of a caller who
    may not see the source.
    """
    svc, own, below = _split_gate_reader(db_session, reader_gate_open=False)

    with pytest.raises(AppError) as exc:
        svc.manifest(SRC, SERIES, "ch-1")

    assert exc.value.status_code == 404
    assert exc.value.code == "source_not_found"
    # Denial before delegation: nothing was read, upstream or cached.
    assert own.calls == []
    assert below.calls == []


def test_bulk_manifest_refuses_on_its_own_line(db_session):
    """Same guard, same reason, one layer up — for every shape of window."""
    svc, own, below = _split_gate_reader(db_session, reader_gate_open=False)

    for window in (["ch-1"], ["ch-1", "ch-2"], ["ch-1", "ch-1"]):
        with pytest.raises(AppError) as exc:
            svc.manifest_batch(SRC, SERIES, window)
        assert (exc.value.status_code, exc.value.code) == (404, "source_not_found"), (
            f"window {window!r} was not refused by the reader's own gate"
        )

    assert own.calls == []
    assert below.calls == []


def test_a_window_of_unresolvable_chapters_cannot_become_an_oracle(db_session):
    """The leak the downstream gate structurally cannot close.

    A chapter key absent from the resolved list is a per-item
    ``chapter_not_found`` — it never reaches ``get_chapter_pages``, so the gate
    that rides on connector resolution never runs for it. With the cache below
    already answering freely, dropping the reader's guard turns this window
    into a 200, and the difference between ``chapter_not_found`` here and
    ``source_not_found`` for a source that was never installed is precisely the
    fact a shut gate is withholding.
    """
    svc, own, below = _split_gate_reader(db_session, reader_gate_open=False)

    with pytest.raises(AppError) as exc:
        svc.manifest_batch(SRC, SERIES, ["no-such-chapter", "nor-this-one"])

    assert exc.value.code == "source_not_found"
    assert own.calls == []
    assert below.calls == []


def test_the_gate_is_the_callers_own_not_a_blanket_refusal(db_session):
    """Same source, same rows, gate OPEN — both paths serve.

    Without this a guard that refused unconditionally would satisfy every
    assertion above, and the tests would pin a broken reader as firmly as a
    correct one.
    """
    svc, _own, _below = _split_gate_reader(db_session, reader_gate_open=True)

    single = svc.manifest(SRC, SERIES, "ch-1")
    window = svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2"])

    assert single["page_count"] == 1
    assert single["next"] == "ch-2"
    assert window["ok_count"] == 2
