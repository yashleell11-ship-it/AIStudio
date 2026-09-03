"""HTTP-level tests for ``routes/updates.py`` (spec §4.5, §7).

settings GET/PUT, notifications list/count/mark-read/mark-all, runs, and the
manual check endpoints. The check sweep's connector call is stubbed so nothing
hits the network; the scheduler pool is down in tests so ``POST /updates/check``
runs synchronously on the request session.
"""

from __future__ import annotations

import pytest

from database.models import UpdateNotification
from services import browse_service

SRC = "mangadex"
SERIES = "nano-machine"


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("upd")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


@pytest.fixture
def api(app, client, acct):
    return client


@pytest.fixture
def stub_chapters(monkeypatch):
    """Stub ``BrowseService.get_chapters`` for the check sweep."""
    box: dict[str, list[dict]] = {"chapters": []}

    def _fake(self, source_id, series_key):  # noqa: ARG001
        return list(box["chapters"])

    monkeypatch.setattr(browse_service.BrowseService, "get_chapters", _fake)
    return box


# --- settings --------------------------------------------------------


def test_settings_get_and_put(api, h):
    got = api.get("/updates/settings", headers=h).json()
    assert set(got) >= {"enabled", "check_interval_minutes", "notify_enabled"}

    put = api.put(
        "/updates/settings",
        json={"enabled": False, "check_interval_minutes": 30, "notify_enabled": False},
        headers=h,
    )
    assert put.status_code == 200, put.text
    assert put.json()["enabled"] is False
    assert put.json()["check_interval_minutes"] == 30

    # interval floor is enforced by the pydantic model (ge=5)
    assert api.put(
        "/updates/settings", json={"check_interval_minutes": 1}, headers=h
    ).status_code == 422


# --- notifications --------------------------------------------------


def _seed_notif(db_session, uid, pid, follow_id, *, chapter_key, is_read=False):
    row = UpdateNotification(
        user_id=uid, profile_id=pid, followed_series_id=follow_id,
        source_id=SRC, series_key=SERIES, chapter_key=chapter_key,
        chapter_title=f"Chapter {chapter_key}", chapter_number=None, is_read=is_read,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_notifications_list_count_mark(api, h, acct, db_session, seed_follow):
    uid, pid = acct
    follow = seed_follow(uid, pid, source_id=SRC, series_key=SERIES)
    n1 = _seed_notif(db_session, uid, pid, follow.id, chapter_key="c1")
    _seed_notif(db_session, uid, pid, follow.id, chapter_key="c2")

    listing = api.get("/updates/notifications", headers=h).json()
    assert {n["chapter_key"] for n in listing} == {"c1", "c2"}

    assert api.get("/updates/notifications/unread-count", headers=h).json()["count"] == 2

    marked = api.patch(f"/updates/notifications/{n1.id}/read", headers=h)
    assert marked.status_code == 200, marked.text
    assert marked.json()["is_read"] is True
    assert api.get(
        "/updates/notifications", params={"unread_only": True}, headers=h
    ).json()[0]["chapter_key"] == "c2"

    all_read = api.post("/updates/notifications/read-all", headers=h).json()
    assert all_read["updated"] == 1
    assert api.get("/updates/notifications/unread-count", headers=h).json()["count"] == 0

    assert api.patch("/updates/notifications/999999/read", headers=h).status_code == 404


def test_notifications_isolated_between_profiles(
    api, as_user, acct, make_profile, db_session, seed_follow
):
    uid, pid = acct
    follow = seed_follow(uid, pid, source_id=SRC, series_key=SERIES)
    _seed_notif(db_session, uid, pid, follow.id, chapter_key="c1")
    other = make_profile(uid, "Other")
    got = api.get(
        "/updates/notifications", headers=as_user(uid, other.id)
    ).json()
    assert got == []


# --- runs -----------------------------------------------------------


def test_runs_list_after_a_check(api, h, stub_chapters):
    resp = api.post("/updates/check", json={}, headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"

    runs = api.get("/updates/runs", headers=h).json()
    assert len(runs) == 1
    assert runs[0]["trigger"] == "manual"
    assert api.get(f"/updates/runs/{runs[0]['id']}", headers=h).status_code == 200
    assert api.get("/updates/runs/999999", headers=h).status_code == 404


# --- the check sweep, end to end via HTTP ---------------------------


def test_check_creates_notifications_for_new_chapters(
    api, h, acct, db_session, seed_follow, stub_chapters
):
    uid, pid = acct
    import json

    known = [{"key": "c1", "number": 1.0, "title": "One", "published_at": None}]
    follow = seed_follow(
        uid, pid, source_id=SRC, series_key=SERIES,
        known_chapters=json.dumps(known), notify=True,
    )
    stub_chapters["chapters"] = [
        {"id": "c1", "number": 1.0, "title": "One"},
        {"id": "c2", "number": 2.0, "title": "Two"},
    ]

    resp = api.post("/updates/check", json={}, headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["new_chapters_found"] == 1

    notifs = api.get("/updates/notifications", headers=h).json()
    assert [n["chapter_key"] for n in notifs] == ["c2"]

    # followed/{id}/check runs the same sweep for one series
    stub_chapters["chapters"].append({"id": "c3", "number": 3.0, "title": "Three"})
    one = api.post(f"/updates/followed/{follow.id}/check", json={}, headers=h)
    assert one.status_code == 200, one.text
    assert one.json()["new_chapters_found"] == 1
