"""AUDIT (shard mature-gate, MG-5): a series' OWN rating gates it on a
GENERAL source, on every browse surface, through the one shared rule.

The source-level gate (``BrowseService._get_connector``) hides whole adult
sources. It said nothing about an adult *series* listed on a general source --
a madara site tagging a work "Smut" -- so a profile with 18+ OFF that could not
see that series in its library (``resolve_tracker_rating`` reads the genre
rating captured at follow time) was still served it by browse, search, series
detail, the chapter list, the reader and the bare pages route.

The rule these pin is ``core.content_rating.resolve_series_rating``: the row's
own rating when known, the source's maturity otherwise, and *unknown* stays
visible -- exactly how the tracker rule already treats an unrated follow, and
for the reason recorded there (unknown-as-adult would blank every unrated
series the moment the gate shut).

One account, two profiles, the gate the only difference between them: a
service that resolved its gate from ``get_settings()`` would answer both the
same way and every assertion here would pass for the wrong reason.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from connectors.models import Chapter, Page, PaginatedSeriesList
from connectors.models import Series as ConnectorSeries
from database.models import SourceSeriesCache
from tests.test_sources_search import _FakeDescriptor, _make_list_installed

SRC = "general-src"
ADULT = "an-adult-series"
SAFE = "a-safe-series"
UNRATED = "an-unrated-series"

CHAPTER = {ADULT: "adult-ch-1", SAFE: "safe-ch-1", UNRATED: "unrated-ch-1"}


def _series(sid: str, title: str, genres: list[str]) -> ConnectorSeries:
    return ConnectorSeries(id=sid, title=title, chapter_count=1, genres=tuple(genres))


CATALOG = {
    ADULT: _series(ADULT, "Explicit Title", ["Smut", "Romance"]),
    SAFE: _series(SAFE, "Wholesome Title", ["Comedy"]),
    UNRATED: _series(UNRATED, "Unrated Title", []),
}


class _GeneralConnector:
    """A general-audience source whose catalog carries one adult-tagged work."""

    is_browsable = True
    is_mature = False

    def list_browse_modes(self):
        return []

    def list_genres(self):
        return []

    def get_series_list(self, page: int, *, sort=None) -> PaginatedSeriesList:
        return PaginatedSeriesList(items=list(CATALOG.values()), api_has_more=False)

    def search_series(self, query: str, page: int, *, sort=None) -> PaginatedSeriesList:
        return self.get_series_list(page, sort=sort)

    def get_series(self, series_id: str) -> ConnectorSeries | None:
        return CATALOG.get(series_id)

    def get_chapters(self, series_id: str) -> list[Chapter]:
        if series_id not in CATALOG:
            return []
        return [
            Chapter(
                id=CHAPTER[series_id],
                series_id=series_id,
                title="Chapter 1",
                number=1.0,
                page_count=1,
            )
        ]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return [
            Page(
                id=f"{chapter_id}/p1",
                chapter_id=chapter_id,
                number=1,
                remote_url="https://example.invalid/p1.jpg",
            )
        ]


@pytest.fixture
def household(make_user, make_profile):
    user = make_user("household")
    return {
        "uid": user.id,
        "kid": make_profile(user.id, "Kid", mature_content_enabled=False).id,
        "grown": make_profile(
            user.id, "Grown", mature_content_enabled=True, sort_order=1
        ).id,
    }


@pytest.fixture
def api(client):
    with patch(
        "services.browse_service.create_connector", return_value=_GeneralConnector()
    ):
        yield client


@pytest.fixture
def kid(as_user, household):
    return as_user(household["uid"], household["kid"])


@pytest.fixture
def grown(as_user, household):
    return as_user(household["uid"], household["grown"])


def _ids(payload: dict) -> set[str]:
    return {item["id"] for item in payload["items"]}


# --- browse ------------------------------------------------------------------


def test_source_search_listing_withholds_the_adult_series_from_a_shut_gate(
    api, kid, grown
):
    """``?query=`` is the listing path that bypasses ``source_browse_cache``,
    so this is ``BrowseService.list_series`` itself answering."""
    shut = api.get(f"/sources/{SRC}/series", params={"query": "title"}, headers=kid)
    open_ = api.get(f"/sources/{SRC}/series", params={"query": "title"}, headers=grown)
    assert shut.status_code == open_.status_code == 200

    assert ADULT not in _ids(shut.json()), "adult series served to a shut gate"
    # The gate hides the adult row, not the listing; unknown stays visible.
    assert {SAFE, UNRATED} <= _ids(shut.json())
    assert ADULT in _ids(open_.json()), "an open gate must still see the series"


def test_federated_search_withholds_the_adult_series_from_a_shut_gate(
    api, kid, grown
):
    descriptors = [_FakeDescriptor(SRC, name="General Source")]
    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ):
        shut = api.get("/sources/search", params={"q": "title"}, headers=kid).json()
        open_ = api.get("/sources/search", params={"q": "title"}, headers=grown).json()

    def titles(payload: dict) -> set[str]:
        return {item["title"] for item in payload["items"]}

    assert "Explicit Title" not in titles(shut)
    assert {"Wholesome Title", "Unrated Title"} <= titles(shut)
    assert "Explicit Title" in titles(open_)


# --- series detail / chapters / reader ---------------------------------------


@pytest.mark.parametrize(
    "suffix",
    ["", "/chapters", f"/chapters/{CHAPTER[ADULT]}/reader"],
    ids=["detail", "chapters", "reader"],
)
def test_series_reads_withhold_the_adult_series_from_a_shut_gate(
    api, kid, grown, suffix
):
    shut = api.get(f"/sources/{SRC}/series/{ADULT}{suffix}", headers=kid)
    # Not-found, never forbidden: existence is not disclosed, exactly like a
    # mature source behind a shut gate.
    assert shut.status_code == 404, shut.text
    assert shut.json()["code"] == "series_not_found"
    assert "Explicit Title" not in shut.text

    assert api.get(f"/sources/{SRC}/series/{ADULT}{suffix}", headers=grown).status_code == 200


@pytest.mark.parametrize("suffix", ["", "/chapters"], ids=["detail", "chapters"])
@pytest.mark.parametrize("series_id", [SAFE, UNRATED], ids=["safe", "unrated"])
def test_a_shut_gate_hides_nothing_that_is_not_adult(api, kid, suffix, series_id):
    assert api.get(f"/sources/{SRC}/series/{series_id}{suffix}", headers=kid).status_code == 200


# --- pages -------------------------------------------------------------------


def _cache_row(series_id: str, rating: str | None) -> SourceSeriesCache:
    # The shape ``SourceCacheService._merge_series_row`` writes: chapters are
    # stored under ``key``, and the rating is the one derived from the genres.
    return SourceSeriesCache(
        source_id=SRC,
        series_key=series_id,
        title=CATALOG[series_id].title,
        content_rating=rating,
        genres=json.dumps(list(CATALOG[series_id].genres)),
        chapters=json.dumps([{"key": CHAPTER[series_id], "number": 1.0}]),
    )


@pytest.fixture
def cached_series(db_session):
    """The adult and safe series as the reader flow leaves them in
    ``source_series_cache``; the unrated one is deliberately NOT cached."""
    db_session.add_all([_cache_row(ADULT, "smut"), _cache_row(SAFE, None)])
    db_session.commit()


def test_pages_of_a_cached_adult_series_are_withheld_from_a_shut_gate(
    api, kid, grown, cached_series
):
    """The bare pages route carries no series id, so the only signal is the
    series the cache remembers that chapter belonging to."""
    shut = api.get(f"/sources/{SRC}/chapters/{CHAPTER[ADULT]}/pages", headers=kid)
    assert shut.status_code == 404, shut.text
    assert shut.json()["code"] == "chapter_not_found"

    assert api.get(f"/sources/{SRC}/chapters/{CHAPTER[ADULT]}/pages", headers=grown).status_code == 200


@pytest.mark.parametrize("series_id", [SAFE, UNRATED], ids=["safe", "unknown"])
def test_pages_stay_visible_when_the_chapter_is_safe_or_unknown(
    api, kid, cached_series, series_id
):
    response = api.get(f"/sources/{SRC}/chapters/{CHAPTER[series_id]}/pages", headers=kid)
    assert response.status_code == 200, response.text
    assert response.json()[0]["chapter_id"] == CHAPTER[series_id]


# --- the GLOBAL caches in front of browse -------------------------------------
#
# ``source_browse_cache`` rows are shared by every profile, so the gate cannot
# be baked into what is stored. It used to be: the rating rule ran when a page
# was FETCHED and the already-filtered page was what got stored, which made the
# rows a caller sees a function of whichever profile happened to warm the row.
# The page is now stored whole (``list_series(apply_gate=False)``) and filtered
# on every serve by ``SourceCacheService._gate_listing``. Both directions are
# asserted below, because the fix cannot be "cache what the caller was shown".

def test_a_cached_browse_page_withholds_the_adult_series_from_a_shut_gate(
    api, kid, grown
):
    """A plain browse (no ``query``) is served from ``source_browse_cache``."""
    warm = api.get(f"/sources/{SRC}/series", headers=grown)
    assert warm.status_code == 200, warm.text
    assert ADULT in _ids(warm.json()), "the open gate never cached the row"

    shut = api.get(f"/sources/{SRC}/series", headers=kid)
    assert shut.status_code == 200, shut.text
    assert ADULT not in _ids(shut.json()), "a cached page served an adult row to a shut gate"


def test_a_cached_browse_page_keeps_the_adult_series_for_an_open_gate(api, kid, grown):
    """The same bug pointing the other way, and the reason the fix cannot just
    be "cache what the caller was shown": a shut-gate browse stores the page
    without the adult row, and the profile that IS allowed it then loses it
    until that row expires."""
    assert api.get(f"/sources/{SRC}/series", headers=kid).status_code == 200

    open_ = api.get(f"/sources/{SRC}/series", headers=grown)
    assert open_.status_code == 200, open_.text
    assert ADULT in _ids(open_.json()), "a shut gate cached a page that hides an adult row from an open one"


# --- the rule itself ---------------------------------------------------------


def test_browsed_and_followed_series_resolve_through_one_rule():
    from core.content_rating import (
        TRACKER_RATING_MATURE,
        TRACKER_RATING_SAFE,
        TRACKER_RATING_UNKNOWN,
        resolve_series_rating,
        resolve_tracker_rating,
    )
    from database.models import FollowedSeries

    # Priority order: the row's own rating, its genres, the source, unknown.
    assert resolve_series_rating("smut") == TRACKER_RATING_MATURE
    assert resolve_series_rating("romance") == TRACKER_RATING_SAFE
    assert resolve_series_rating(None) == TRACKER_RATING_UNKNOWN
    assert resolve_series_rating(None, ["Action", "Smut"]) == TRACKER_RATING_MATURE
    # Genres only ever raise the verdict: a row tagged "Action" is unknown, not safe.
    assert resolve_series_rating(None, ["Action"]) == TRACKER_RATING_UNKNOWN
    assert resolve_series_rating(None, source_mature=True) == TRACKER_RATING_MATURE
    # The row's own rating beats the source's, as it does for a follow.
    assert resolve_series_rating("romance", source_mature=True) == TRACKER_RATING_SAFE

    # A follow captures its rating from the same genres at follow time, so the
    # library rule and the browse rule must answer alike for the same signals.
    for rating in ("smut", "romance", None):
        follow = FollowedSeries(content_rating=rating, mature_override=None)
        assert resolve_tracker_rating(follow, None) == resolve_series_rating(rating)
