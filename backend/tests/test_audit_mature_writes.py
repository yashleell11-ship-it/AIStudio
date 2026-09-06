"""The library's *write* routes answer the 18+ gate exactly as its reads do.

Two regressions this pins (audit MG-3, MG-4):

* ``PATCH /library/series/{id}`` and a re-``POST /library/follow`` used to
  return ``serialize(row)`` for a row ``GET /library/series/{id}`` 404s for the
  same profile — title, cover and the whole ``known_chapters`` array, i.e. the
  write path disclosed what every read path conceals.
* ``POST /library/follow`` on a *mature source* used to succeed while the gate
  was shut: the source gate ran only inside the ``try`` that lets a follow
  survive a source being down, so the 404 was swallowed and the profile ended
  up owning a follow it can neither see nor manage.

Denial is 404 throughout, never 403 — a 403 confirms the row exists.
"""

from __future__ import annotations

import pytest

import connectors.registry as registry
from connectors.base import SourceConnector
from connectors.models import BrowseMode, PaginatedSeriesList
from database.models import FollowedSeries
from services.browse_service import get_browse_service
from tests._fakes import FakeBrowse

SRC = "mangadex"
ADULT = "an-adult-series"
MATURE_SRC = "stub_mature_write_gate"
TITLE = "Very Adult Title"
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
def mature_source():
    registry.register_connector(MATURE_SRC, StubMatureSource)
    yield
    registry._REGISTRY.pop(MATURE_SRC, None)
    registry._INSTANCE_CACHE.pop(MATURE_SRC, None)


@pytest.fixture
def kid(make_user, make_profile):
    user = make_user("gated-household")
    profile = make_profile(user.id, "Kid", mature_content_enabled=False)
    return {"uid": user.id, "pid": profile.id}


@pytest.fixture
def grown(make_user, make_profile):
    user = make_user("open-household")
    profile = make_profile(user.id, "Grown", mature_content_enabled=True)
    return {"uid": user.id, "pid": profile.id}


def _adult_follow(seed_follow, who) -> FollowedSeries:
    return seed_follow(
        who["uid"],
        who["pid"],
        source_id=SRC,
        series_key=ADULT,
        title=TITLE,
        known_chapters=CHAPTERS,
        mature_override=True,
    )


def test_patch_of_a_gated_series_answers_like_get(
    client, as_user, db_session, kid, seed_follow
):
    row = _adult_follow(seed_follow, kid)
    headers = as_user(kid["uid"], kid["pid"])
    assert client.get(f"/library/series/{row.id}", headers=headers).status_code == 404

    resp = client.patch(
        f"/library/series/{row.id}", json={"sort_order": 5}, headers=headers
    )
    assert resp.status_code == 404, resp.text
    assert TITLE not in resp.text
    assert "Secret chapter title" not in resp.text
    db_session.expire_all()
    assert db_session.get(FollowedSeries, row.id).sort_order == 0


def test_refollow_of_a_gated_series_does_not_echo_it(
    client, as_user, kid, seed_follow
):
    row = _adult_follow(seed_follow, kid)
    headers = as_user(kid["uid"], kid["pid"])

    resp = client.post(
        "/library/follow",
        json={"source_id": SRC, "series_key": ADULT},
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
    assert TITLE not in resp.text
    assert "Secret chapter title" not in resp.text
    assert str(row.id) not in resp.text


def test_follow_on_a_hidden_mature_source_is_refused(
    client, as_user, db_session, kid, mature_source
):
    headers = as_user(kid["uid"], kid["pid"])
    # Browse denies the source's existence for this profile; follow must agree.
    assert (
        client.get(f"/sources/{MATURE_SRC}/browse-modes", headers=headers).status_code
        == 404
    )

    resp = client.post(
        "/library/follow",
        json={"source_id": MATURE_SRC, "series_key": "s1"},
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
    assert db_session.query(FollowedSeries).filter_by(source_id=MATURE_SRC).all() == []


def test_an_open_gate_still_patches_and_refollows(
    client, as_user, db_session, grown, seed_follow
):
    row = _adult_follow(seed_follow, grown)
    headers = as_user(grown["uid"], grown["pid"])

    patched = client.patch(
        f"/library/series/{row.id}", json={"sort_order": 5}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["sort_order"] == 5

    again = client.post(
        "/library/follow",
        json={"source_id": SRC, "series_key": ADULT},
        headers=headers,
    )
    assert again.status_code == 200, again.text
    assert again.json()["title"] == TITLE


# --- the rest of the same root cause ---------------------------------------
#
# A follow addressed by id or by key without the gate: DELETE is the same
# existence oracle PATCH was, and a *first* follow can land already hidden.

SAFE = "a-safe-series"


@pytest.fixture
def api(client):
    """``client`` whose browse stub rates ``ADULT`` adult by genre alone —
    the source itself is not mature, so this is the series gate, not the
    source gate, that the follow path has to answer."""
    client.app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(
        {
            (SRC, ADULT): {
                "meta": {"title": TITLE, "genres": ["Action", "Adult"]},
                "chapters": [
                    {"id": "c1", "number": 1, "title": "Secret chapter title"}
                ],
            },
            (SRC, SAFE): {
                "meta": {"title": "Safe Title", "genres": ["Action"]},
                "chapters": [{"id": "c1", "number": 1, "title": "One"}],
            },
        }
    )
    yield client
    client.app.dependency_overrides.pop(get_browse_service, None)


def test_unfollow_of_a_gated_series_answers_like_get(
    client, as_user, db_session, kid, seed_follow
):
    row = _adult_follow(seed_follow, kid)
    headers = as_user(kid["uid"], kid["pid"])
    assert client.get(f"/library/series/{row.id}", headers=headers).status_code == 404

    assert client.delete(f"/library/follow/{row.id}", headers=headers).status_code == 404
    # Refused means untouched: the row is still there for a gate that is open.
    db_session.expire_all()
    assert db_session.get(FollowedSeries, row.id) is not None


def test_first_follow_that_would_land_hidden_is_refused(api, as_user, db_session, kid):
    headers = as_user(kid["uid"], kid["pid"])
    resp = api.post(
        "/library/follow", json={"source_id": SRC, "series_key": ADULT}, headers=headers
    )
    assert resp.status_code == 404, resp.text
    assert TITLE not in resp.text
    assert "Secret chapter title" not in resp.text
    assert (
        db_session.query(FollowedSeries).filter_by(source_id=SRC, series_key=ADULT).all()
        == []
    )

    # Same source, same profile, no adult genre: follows as before. (No signal
    # resolves to ``unknown``, never to ``mature`` -- see resolve_tracker_rating.)
    ok = api.post(
        "/library/follow", json={"source_id": SRC, "series_key": SAFE}, headers=headers
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["rating"] != "mature"


def test_an_open_gate_follows_the_same_series_and_unfollows_it(
    api, as_user, db_session, grown
):
    headers = as_user(grown["uid"], grown["pid"])
    created = api.post(
        "/library/follow", json={"source_id": SRC, "series_key": ADULT}, headers=headers
    )
    assert created.status_code == 200, created.text
    assert created.json()["rating"] == "mature"
    fid = created.json()["id"]

    assert api.delete(f"/library/follow/{fid}", headers=headers).status_code == 204
    db_session.expire_all()
    assert db_session.get(FollowedSeries, fid) is None


# --- the source gate: unknown and hidden must be one answer -----------------

UNKNOWN_SRC = "no_such_source_at_all"


def test_follow_on_an_unregistered_source_is_refused(
    client, as_user, db_session, kid
):
    """The hidden-source bug was the visible half of "follow never checked
    ``source_id`` at all": an id no connector claims used to be accepted too,
    leaving an orphan follow the sweep would walk forever."""
    headers = as_user(kid["uid"], kid["pid"])
    resp = client.post(
        "/library/follow",
        json={"source_id": UNKNOWN_SRC, "series_key": "s1"},
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
    assert (
        db_session.query(FollowedSeries).filter_by(source_id=UNKNOWN_SRC).all() == []
    )


def test_a_hidden_source_and_an_unknown_one_are_refused_alike(
    client, as_user, kid, mature_source
):
    """Otherwise the refusal is itself the rating oracle: a caller who may not
    be told the source exists would still learn it is adult from a
    differently-shaped no. ``details`` may only echo the id the caller sent.
    """
    headers = as_user(kid["uid"], kid["pid"])

    def _follow(source_id: str):
        return client.post(
            "/library/follow",
            json={"source_id": source_id, "series_key": "s1"},
            headers=headers,
        )

    hidden = _follow(MATURE_SRC)
    unknown = _follow(UNKNOWN_SRC)
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.json()["code"] == unknown.json()["code"]
    assert hidden.json()["message"] == unknown.json()["message"]
    assert hidden.json()["details"] == {"source_id": MATURE_SRC}
    assert unknown.json()["details"] == {"source_id": UNKNOWN_SRC}
    # No rating reaches a caller the gate is shut against, on either answer.
    assert "rating" not in hidden.json()
    assert "content_rating" not in hidden.json()
