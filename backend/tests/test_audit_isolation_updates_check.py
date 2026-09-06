"""Audit (shard: isolation) — the instance-wide sweep and the run log are
admin surfaces.

A non-admin's id-less ``POST /updates/check`` used to run the same unfiltered
statement the scheduler does, sweeping every account's ``followed_series``
(rewriting their snapshots and consuming their notification windows), and
``GET /updates/runs`` handed anyone the global run log with the aggregate
counts. A member's id-less check is now their own library; the instance-wide
sweep and the run log are admin-only.
"""

from __future__ import annotations

import json

import pytest

from database.models import FollowedSeries, UpdateNotification
from services import browse_service
from services.update_service import UpdateService

SRC = "mangadex"
KNOWN = [{"key": "c1", "number": 1.0, "title": "One", "published_at": None}]
LIVE = [
    {"id": "c1", "number": 1.0, "title": "One"},
    {"id": "c2", "number": 2.0, "title": "Two"},
]


@pytest.fixture
def stub_chapters(monkeypatch):
    box: dict[str, list[dict]] = {"chapters": []}

    def _fake(self, source_id, series_key):  # noqa: ARG001
        return list(box["chapters"])

    monkeypatch.setattr(browse_service.BrowseService, "get_chapters", _fake)
    return box


def _follow(seed_follow, user, profile, key="s"):
    return seed_follow(
        user.id, profile.id, source_id=SRC, series_key=key,
        known_chapters=json.dumps(KNOWN), notify=True,
    )


def test_member_idless_check_never_reaches_another_account(
    client, db_session, make_user, make_profile, as_user, seed_follow, stub_chapters
):
    a = make_user("victim")
    a_prof = make_profile(a.id, "Main")
    follow = _follow(seed_follow, a, a_prof)

    b = make_user("member")  # is_admin=False, and no followed series
    b_prof = make_profile(b.id, "Main")
    stub_chapters["chapters"] = list(LIVE)

    resp = client.post("/updates/check", json={}, headers=as_user(b.id, b_prof.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["series_checked"] == 0
    assert body["new_chapters_found"] == 0

    db_session.expire_all()
    row = db_session.get(FollowedSeries, follow.id)
    assert row.last_checked_at is None
    assert [c["key"] for c in json.loads(row.known_chapters)] == ["c1"]
    assert db_session.query(UpdateNotification).count() == 0

    # The owner's own id-less check still covers their library.
    mine = client.post("/updates/check", json={}, headers=as_user(a.id, a_prof.id))
    assert mine.status_code == 200, mine.text
    assert mine.json()["series_checked"] == 1
    assert mine.json()["new_chapters_found"] == 1
    assert (
        db_session.query(UpdateNotification)
        .filter_by(followed_series_id=follow.id)
        .count()
        == 1
    )


def test_member_idless_check_stays_inside_the_active_profile(
    client, db_session, make_user, make_profile, as_user, seed_follow, stub_chapters
):
    user = make_user("household")
    main = make_profile(user.id, "Main")
    other = make_profile(user.id, "Other", sort_order=1)
    on_main = _follow(seed_follow, user, main, key="main-series")
    on_other = _follow(seed_follow, user, other, key="other-series")
    stub_chapters["chapters"] = list(LIVE)

    resp = client.post("/updates/check", json={}, headers=as_user(user.id, main.id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["series_checked"] == 1

    db_session.expire_all()
    assert db_session.get(FollowedSeries, on_main.id).last_checked_at is not None
    assert db_session.get(FollowedSeries, on_other.id).last_checked_at is None


def test_admin_idless_check_sweeps_every_account(
    client, db_session, make_user, make_profile, as_user, seed_follow, stub_chapters
):
    a = make_user("someone")
    a_prof = make_profile(a.id, "Main")
    follow = _follow(seed_follow, a, a_prof)
    admin = make_user("root", is_admin=True)
    stub_chapters["chapters"] = list(LIVE)

    resp = client.post("/updates/check", json={}, headers=as_user(admin.id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["series_checked"] == 1
    assert resp.json()["new_chapters_found"] == 1

    db_session.expire_all()
    assert db_session.get(FollowedSeries, follow.id).last_checked_at is not None


def test_run_log_is_admin_only(client, make_user, make_profile, as_user, stub_chapters):
    member = make_user("member")
    m_prof = make_profile(member.id, "Main")
    mh = as_user(member.id, m_prof.id)
    ah = as_user(make_user("root", is_admin=True).id)

    assert client.post("/updates/check", json={}, headers=ah).status_code == 200

    listing = client.get("/updates/runs", headers=mh)
    assert listing.status_code == 403, listing.text
    assert listing.json()["code"] == "forbidden"

    runs = client.get("/updates/runs", headers=ah)
    assert runs.status_code == 200, runs.text
    assert len(runs.json()) == 1
    run_id = runs.json()[0]["id"]
    assert client.get(f"/updates/runs/{run_id}", headers=mh).status_code == 403
    assert client.get(f"/updates/runs/{run_id}", headers=ah).status_code == 200


def test_member_idless_check_hands_the_worker_its_own_ids_only(
    client, make_user, make_profile, as_user, seed_follow, monkeypatch
):
    """With the pool up the route queues ids for a *system*-scoped worker, so
    the scoping has to be complete before they leave the request — and an
    empty library must queue ``[]``, never ``None`` (``None`` is the sweep)."""
    from routes import updates as updates_routes

    class _RunningManager:
        is_running = True

        def __init__(self) -> None:
            self.triggered: list[object] = []

        def trigger_check(self, *, trigger, tracker_ids=None):  # noqa: ARG002
            self.triggered.append(tracker_ids)
            return True

    manager = _RunningManager()
    monkeypatch.setattr(updates_routes, "get_update_manager", lambda: manager)

    owner = make_user("owner")
    o_prof = make_profile(owner.id, "Main")
    mine = seed_follow(owner.id, o_prof.id, source_id=SRC, series_key="mine")
    other = make_user("other")
    ot_prof = make_profile(other.id, "Main")
    seed_follow(other.id, ot_prof.id, source_id=SRC, series_key="theirs")
    empty = make_user("empty")
    e_prof = make_profile(empty.id, "Main")
    admin = make_user("root", is_admin=True)

    queued = {"queued": True, "trigger": "manual"}
    assert client.post(
        "/updates/check", json={}, headers=as_user(owner.id, o_prof.id)
    ).json() == queued
    assert client.post(
        "/updates/check", json={}, headers=as_user(empty.id, e_prof.id)
    ).json() == queued
    assert client.post("/updates/check", json={}, headers=as_user(admin.id)).json() == queued

    assert manager.triggered == [[mine.id], [], None]


def test_an_empty_id_list_checks_nothing_not_everything(
    db_session, make_user, make_profile, seed_follow, stub_chapters
):
    """``followed_ids or tracker_ids`` collapsed ``[]`` into the full sweep."""
    user = make_user("bystander")
    profile = make_profile(user.id, "Main")
    follow = _follow(seed_follow, user, profile)
    stub_chapters["chapters"] = list(LIVE)

    for kwargs in ({"followed_ids": []}, {"tracker_ids": []}):
        result = UpdateService(db_session, system=True).run_check(
            trigger="manual", **kwargs
        )
        assert result["status"] == "completed"
        assert result["series_checked"] == 0, kwargs

    db_session.refresh(follow)
    assert follow.last_checked_at is None
