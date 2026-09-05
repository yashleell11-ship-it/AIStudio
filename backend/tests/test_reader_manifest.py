"""``GET /reader/chapter/manifest`` — the client download plan (spec §4.1, §7).

The manifest is the ordered page list (number + proxy URL + the source's own
width/height when it reports them), chapter number, and prev/next chapter keys.
No bytes. Tested against a stub connector.
"""

from __future__ import annotations

import pytest

from core.errors import AppError
from services.browse_service import get_browse_service
from services.reader_service import ReaderService
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "omniscient-reader"

FIXTURE = {
    (SRC, SERIES): {
        "meta": {"title": "Omniscient Reader"},
        "chapters": [
            {"id": "ch-1", "number": 1.0, "title": "Prologue"},
            {"id": "ch-2", "number": 2.0, "title": "Episode 1"},
            {"id": "ch-3", "number": 3.0, "title": "Episode 2"},
        ],
        "pages": {
            "ch-2": [
                {
                    "number": 1,
                    "image_url": "/sources/mangadex/pages/p1/image",
                    "width": 720,
                    "height": 14668,
                },
                {
                    "number": 2,
                    "image_url": "/sources/mangadex/pages/p2/image",
                    "width": 720,
                    "height": 9600,
                },
                # No dimensions: the same connector can know some pages and not
                # others, and the manifest must still answer for every page.
                {"number": 3, "image_url": "/sources/mangadex/pages/p3/image"},
            ]
        },
    }
}


def test_manifest_shape(db_session):
    svc = ReaderService(FakeBrowse(FIXTURE))
    m = svc.manifest(SRC, SERIES, "ch-2")

    assert m["source_id"] == SRC
    assert m["series_key"] == SERIES
    assert m["chapter_key"] == "ch-2"
    assert m["chapter_number"] == 2.0
    assert m["page_count"] == 3
    assert m["pages"] == [
        {
            "number": 1,
            "url": "/sources/mangadex/pages/p1/image",
            "width": 720,
            "height": 14668,
        },
        {
            "number": 2,
            "url": "/sources/mangadex/pages/p2/image",
            "width": 720,
            "height": 9600,
        },
        # Present and null rather than absent, so the client branches on a value.
        {
            "number": 3,
            "url": "/sources/mangadex/pages/p3/image",
            "width": None,
            "height": None,
        },
    ]
    assert m["prev"] == "ch-1"
    assert m["next"] == "ch-3"
    # no bytes, no hashes in v1
    assert "sha256" not in m["pages"][0]


def test_manifest_prev_none_at_first_chapter(db_session):
    fixture = {
        (SRC, SERIES): {
            **FIXTURE[(SRC, SERIES)],
            "pages": {"ch-1": [{"number": 1, "image_url": "/x"}]},
        }
    }
    m = ReaderService(FakeBrowse(fixture)).manifest(SRC, SERIES, "ch-1")
    assert m["prev"] is None
    assert m["next"] == "ch-2"


def test_manifest_unknown_chapter_is_404(db_session):
    svc = ReaderService(FakeBrowse(FIXTURE))
    with pytest.raises(AppError) as exc:
        svc.manifest(SRC, SERIES, "ch-does-not-exist")
    assert exc.value.status_code == 404


def test_manifest_endpoint(app, client):
    app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(FIXTURE)
    resp = client.get(
        "/reader/chapter/manifest",
        params={"source": SRC, "series": SERIES, "chapter": "ch-2"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_count"] == 3
    assert body["next"] == "ch-3"


# --- the chapter list comes from the cache, not the connector --------------


def test_manifest_serves_the_chapter_list_from_the_source_cache(db_session):
    """A second chapter open must not re-fetch the series from upstream.

    The manifest needs the chapter list only to locate the chapter and name its
    neighbours. Asking the connector for it meant a live series-page fetch per
    chapter open — measured at 272 ms and 355 ms against the owner's own
    asurascans follows, versus ~1 ms from ``source_series_cache``.
    """
    browse = FakeBrowse(FIXTURE)
    svc = ReaderService(browse, db=db_session)

    def kinds(calls):
        return {c.split(":", 1)[0] for c in calls}

    svc.manifest(SRC, SERIES, "ch-2")
    assert "get_chapters" in kinds(browse.calls), (
        "first open should populate the cache"
    )

    browse.calls.clear()
    second = svc.manifest(SRC, SERIES, "ch-3")

    assert second["prev"] == "ch-2" and second["next"] is None
    assert "get_chapters" not in kinds(browse.calls), (
        "chapter list should have come from source_series_cache; "
        f"connector calls were {browse.calls}"
    )
    assert "get_series" not in kinds(browse.calls), (
        "the series page is the expensive upstream fetch and must not be "
        f"repeated; connector calls were {browse.calls}"
    )
    # Pages are per-chapter and genuinely live — they must still be fetched.
    assert "get_chapter_pages" in kinds(browse.calls)


def test_manifest_refetches_when_the_chapter_is_newer_than_the_cache(db_session):
    """A chapter published after the cached list was written still resolves.

    This is what makes serving the reader from a cache safe: the one chapter a
    stale list cannot contain is the newest one, which is exactly the chapter
    the owner is most likely to be opening.
    """
    browse = FakeBrowse(FIXTURE)
    svc = ReaderService(browse, db=db_session)
    svc.manifest(SRC, SERIES, "ch-2")  # cache now holds ch-1..ch-3

    # Upstream publishes ch-4 while the cached row is still inside its TTL.
    browse.series[(SRC, SERIES)]["chapters"].append(
        {"id": "ch-4", "number": 4.0, "title": "Episode 3"}
    )
    browse.series[(SRC, SERIES)]["pages"]["ch-4"] = [
        {"number": 1, "image_url": "/sources/mangadex/pages/p9/image"}
    ]

    m = svc.manifest(SRC, SERIES, "ch-4")

    assert m["chapter_number"] == 4.0
    assert m["prev"] == "ch-3"
    assert m["next"] is None


def test_manifest_recovers_from_a_cached_empty_chapter_list(db_session):
    """One upstream blip must not make the reader deny the series for 6 hours.

    ``SourceCacheService.get_series_meta`` treats a row holding ``[]`` as a
    *fresh* hit — the ``chapters is not None`` guard is about browse
    write-through rows, not emptiness — so a source that answered once with no
    chapters pins that answer for ``source_cache_ttl_minutes`` (6 hours).
    Before the manifest read from this cache it went to the connector every
    time and could not be poisoned this way, so the live retry has to cover the
    empty list too, not only a list that is merely missing the newest chapter.
    """
    browse = FakeBrowse(FIXTURE)
    browse.series[(SRC, SERIES)]["chapters"] = []
    svc = ReaderService(browse, db=db_session)

    with pytest.raises(AppError) as excinfo:
        svc.manifest(SRC, SERIES, "ch-2")
    assert excinfo.value.code == "series_not_found"  # cache now holds []

    # Upstream recovers well inside the 6-hour TTL.
    browse.series[(SRC, SERIES)]["chapters"] = [
        {"id": "ch-1", "number": 1.0, "title": "Prologue"},
        {"id": "ch-2", "number": 2.0, "title": "Episode 1"},
        {"id": "ch-3", "number": 3.0, "title": "Episode 2"},
    ]

    m = svc.manifest(SRC, SERIES, "ch-2")

    assert m["chapter_number"] == 2.0
    assert m["prev"] == "ch-1"
    assert m["next"] == "ch-3"


def test_manifest_still_404s_for_a_chapter_that_does_not_exist(db_session):
    """The refetch must not turn "no such chapter" into something else."""
    browse = FakeBrowse(FIXTURE)
    svc = ReaderService(browse, db=db_session)
    svc.manifest(SRC, SERIES, "ch-2")

    with pytest.raises(AppError) as excinfo:
        svc.manifest(SRC, SERIES, "ch-does-not-exist")
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "chapter_not_found"


@pytest.mark.parametrize("requested", ["/ch-2", "ch-2/", "/ch-2/"])
def test_manifest_tolerates_surrounding_slashes_on_the_chapter_key(
    db_session, requested
):
    """Connectors are not consistent about leading/trailing separators.

    ``_locate`` falls back to a ``strip("/")`` comparison for exactly this, and
    the fallback is what keeps a link built with one convention resolving
    against a chapter list stored with the other. Without it these are 404s.
    """
    svc = ReaderService(FakeBrowse(FIXTURE), db=db_session)
    m = svc.manifest(SRC, SERIES, requested)

    assert m["chapter_number"] == 2.0
    assert m["prev"] == "ch-1"
    assert m["next"] == "ch-3"


def test_manifest_locates_the_chapter_in_a_cache_shaped_list(db_session):
    """``source_series_cache`` stores chapters under ``key``, connectors under
    ``id``. The manifest now reads from both, so the neighbours it names must
    be right in either shape."""
    from services.reader_service import _chapter_key, _locate

    cache_shaped = [{"key": "ch-1"}, {"key": "ch-2"}, {"key": "ch-3"}]
    connector_shaped = [{"id": "ch-1"}, {"id": "ch-2"}, {"id": "ch-3"}]

    assert _locate(cache_shaped, "ch-2") == 1
    assert _locate(connector_shaped, "ch-2") == 1
    assert _chapter_key({"key": "k"}) == "k"
    assert _chapter_key({"id": "i"}) == "i"
    assert _chapter_key({}) == ""


def test_manifest_applies_the_18plus_gate_before_reading_the_cache(db_session):
    """A gated caller must not be able to tell a cached mature source apart
    from one that was never installed.

    The gate used to be implicit: the chapter list came from
    ``BrowseService.get_chapters``, which resolves the connector and therefore
    404s ``source_not_found`` before the method can say anything else. Serving
    that list from ``source_series_cache`` skips the connector — cache rows are
    global, the gate is per-caller — so an unknown chapter on a cached mature
    source answered ``chapter_not_found`` instead, which is one bit more than a
    closed gate is supposed to disclose.
    """
    SRC = "toonily"
    fixture = {
        (SRC, SERIES): {
            "meta": {"title": "Gated"},
            "chapters": [{"id": "ch-1", "number": 1.0, "title": "One"}],
            "pages": {"ch-1": [{"number": 1, "image_url": "/x"}]},
        }
    }
    browse = FakeBrowse(fixture)
    svc = ReaderService(browse, db=db_session)
    svc.manifest(SRC, SERIES, "ch-1")  # gate open: warms source_series_cache

    browse.mature_sources = {SRC}
    browse.gate_open = False

    for chapter_key in ("ch-1", "no-such-chapter"):
        with pytest.raises(AppError) as excinfo:
            svc.manifest(SRC, SERIES, chapter_key)
        assert excinfo.value.status_code == 404
        assert excinfo.value.code == "source_not_found", (
            f"{chapter_key!r} disclosed that the source exists"
        )
