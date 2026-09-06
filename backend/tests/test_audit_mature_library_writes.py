"""AUDIT (shard mature-gate): library write routes echo gated rows / bypass the source gate.

1. ``PATCH /library/series/{id}`` (``FollowedSeriesService.patch``) resolves
   the row through ``_get_owned`` only — no rating check — and returns the full
   ``serialize(row)``: title, cover_url, rating and the entire ``known_chapters``
   array. ``GET /library/series/{id}`` 404s the same row for the same profile.
   ``BookmarkService._echo`` strips enrichment from a gated row on its write
   path; the library's write path does not.
2. ``POST /library/follow`` for an already-followed adult series returns the
   same full payload.
3. ``POST /library/follow`` on a *mature source* while the gate is shut
   succeeds: the 404 ``ensure_visible`` would raise is swallowed by the
   ``except Exception`` around ``get_series``/``get_chapters`` (follow must
   survive a source being down), so a row is created for a source the profile
   is not allowed to know exists.
"""

from __future__ import annotations

import pytest

import connectors.registry as registry
from connectors.base import SourceConnector
from connectors.models import BrowseMode, PaginatedSeriesList
from database.models import FollowedSeries

SRC = "mangadex"
ADULT = "an-adult-series"
MATURE_SRC = "stub_mature_audit_follow"
CHAPTERS = '[{"key": "c1", "number": 1, "title": "Secret chapter title"}]'


class StubMatureSource(SourceConnector):
    SOURCE_TYPE = MATURE_SRC
    DISPLAY_NAME = "Stub Mature"
    DESCRIPTION = "Test-only mature source."
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True
    CONTENT_KIND = "manga"

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    def list_browse_modes(self):
        return [BrowseMode(id="default", label="Browse")]

    def get_series_list(self, page, *, sort=None):
        return PaginatedSeriesList(items=[], page=page, page_size=20, total=0)

    def search_series(self, query, page, *, sort=None):
        return self.get_series_list(page, sort=sort)

    def get_series(self, series_id):
        return None

    def get_chapters(self, series_id):
        return []

    def get_chapter_pages(self, chapter_id):
        return []


@pytest.fixture
def stub_mature_source():
    registry.register_connector(MATURE_SRC, StubMatureSource)
    yield
    registry._REGISTRY.pop(MATURE_SRC, None)
    registry._INSTANCE_CACHE.pop(MATURE_SRC, None)


@pytest.fixture
def kid(make_user, make_profile):
    user = make_user("household")
    return {"uid": user.id, "pid": make_profile(user.id, "Kid", mature_content_enabled=False).id}


@pytest.fixture
def adult_follow(kid, seed_follow):
    return seed_follow(
        kid["uid"], kid["pid"], source_id=SRC, series_key=ADULT,
        title="Very Adult Title", known_chapters=CHAPTERS, mature_override=True,
    )


def test_patch_answers_like_get_for_a_gated_series(client, as_user, kid, adult_follow):
    headers = as_user(kid["uid"], kid["pid"])
    assert client.get(f"/library/series/{adult_follow.id}", headers=headers).status_code == 404
    resp = client.patch(f"/library/series/{adult_follow.id}", json={"sort_order": 5}, headers=headers)
    assert resp.status_code == 404, resp.json()


def test_refollow_does_not_echo_a_gated_series(client, as_user, kid, adult_follow):
    headers = as_user(kid["uid"], kid["pid"])
    resp = client.post("/library/follow", json={"source_id": SRC, "series_key": ADULT}, headers=headers)
    body = resp.json()
    assert "Very Adult Title" not in str(body), body
    assert "Secret chapter title" not in str(body), body


def test_follow_on_a_hidden_source_is_refused(client, as_user, kid, db_session, stub_mature_source):
    headers = as_user(kid["uid"], kid["pid"])
    # Browse says this source does not exist for this profile.
    assert client.get(f"/sources/{MATURE_SRC}/browse-modes", headers=headers).status_code == 404
    resp = client.post(
        "/library/follow", json={"source_id": MATURE_SRC, "series_key": "s1"}, headers=headers
    )
    assert resp.status_code == 404, resp.json()
    rows = db_session.query(FollowedSeries).filter_by(source_id=MATURE_SRC).all()
    assert rows == []
