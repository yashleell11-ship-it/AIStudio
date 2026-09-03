"""Instance-global settings writes require admin (audit findings 1/2/4/5/6/7).

``PUT /updates/settings`` and the global branches of ``PUT /settings`` used to
be reachable by any authenticated account: a non-admin could disable everyone's
update notifications, retune the sweep interval and cache TTL, and — worst —
flip the instance-wide 18+ default (the gate fallback for unscoped requests
AND the seed for every newly created profile) simply by omitting or garbling
``X-Profile-Id``.

Now:
* ``PUT /updates/settings`` — admin only.
* ``PUT /settings`` ``updates_*`` / ``source_cache_ttl_minutes`` — admin only.
* ``PUT /settings`` ``mature_content_enabled`` — per-profile self-service with
  a valid owned header; 404 for a foreign/garbled header (a write never
  silently degrades to the global bucket); admin only with no header (the
  global default).

Also covered: the scheduler actually honours ``enabled`` now — it used to
change only the sleep interval.
"""

from __future__ import annotations

import json

import pytest

from core.config import get_settings
from database.models import ReadingProfile, UpdateSettings


@pytest.fixture
def accounts(make_user, make_profile):
    admin = make_user("owner", is_admin=True)
    member = make_user("member")  # non-admin
    member_profile = make_profile(member.id, "Member Main")
    admin_profile = make_profile(admin.id, "Owner Main")
    return {
        "admin": admin,
        "member": member,
        "member_profile": member_profile,
        "admin_profile": admin_profile,
    }


@pytest.fixture
def settings_file(monkeypatch, tmp_path):
    """Point the persisted global settings at a scratch file so global writes
    are observable and never touch the real config/settings.json."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr("core.config.SETTINGS_PATH", path)
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# PUT /updates/settings
# ---------------------------------------------------------------------------


def test_non_admin_cannot_rewrite_global_update_settings(
    client, as_user, accounts, db_session
):
    h = as_user(accounts["member"].id)
    response = client.put(
        "/updates/settings", json={"notify_enabled": False}, headers=h
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    # The singleton row was not touched.
    row = db_session.get(UpdateSettings, 1)
    assert row is None or bool(row.notify_enabled)


def test_admin_can_rewrite_global_update_settings(client, as_user, accounts):
    h = as_user(accounts["admin"].id)
    response = client.put(
        "/updates/settings", json={"notify_enabled": False}, headers=h
    )
    assert response.status_code == 200, response.text
    assert response.json()["notify_enabled"] is False


# ---------------------------------------------------------------------------
# PUT /settings: the updates_* passthrough and the cache TTL are global too
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"updates_notify_enabled": False},
        {"updates_enabled": False},
        {"updates_check_interval_minutes": 5},
        {"source_cache_ttl_minutes": 5},
    ],
)
def test_non_admin_cannot_write_global_fields_via_unified_settings(
    client, as_user, accounts, body
):
    h = as_user(accounts["member"].id, accounts["member_profile"].id)
    response = client.put("/settings", json=body, headers=h)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"


def test_admin_can_write_global_fields_via_unified_settings(
    client, as_user, accounts, settings_file
):
    h = as_user(accounts["admin"].id, accounts["admin_profile"].id)
    response = client.put(
        "/settings",
        json={"updates_notify_enabled": False, "source_cache_ttl_minutes": 30},
        headers=h,
    )
    assert response.status_code == 200, response.text
    assert response.json()["updates"]["notify_enabled"] is False
    assert json.loads(settings_file.read_text())["source_cache_ttl_minutes"] == 30


def test_mixed_body_applies_nothing_when_admin_gate_fails(
    client, as_user, accounts, db_session, settings_file
):
    """A non-admin body mixing a permitted per-profile toggle with a gated
    global field must 403 without applying either half."""
    h = as_user(accounts["member"].id, accounts["member_profile"].id)
    response = client.put(
        "/settings",
        json={"mature_content_enabled": True, "updates_notify_enabled": False},
        headers=h,
    )
    assert response.status_code == 403
    db_session.expire_all()
    profile = db_session.get(ReadingProfile, accounts["member_profile"].id)
    assert not profile.mature_content_enabled
    assert not settings_file.exists()


# ---------------------------------------------------------------------------
# PUT /settings: the mature_content_enabled routing
# ---------------------------------------------------------------------------


def test_profile_owner_can_still_toggle_own_profile_gate(
    client, as_user, accounts, db_session
):
    h = as_user(accounts["member"].id, accounts["member_profile"].id)
    response = client.put(
        "/settings", json={"mature_content_enabled": True}, headers=h
    )
    assert response.status_code == 200, response.text
    db_session.expire_all()
    profile = db_session.get(ReadingProfile, accounts["member_profile"].id)
    assert bool(profile.mature_content_enabled)
    # The global default was NOT written.
    assert get_settings().mature_content_enabled is False


def test_omitting_profile_header_no_longer_flips_global_default(
    client, as_user, accounts, settings_file
):
    """The finding-2/4 attack: a non-admin PUT with no X-Profile-Id used to
    rewrite the instance-wide 18+ default."""
    h = as_user(accounts["member"].id)  # no X-Profile-Id header
    response = client.put(
        "/settings", json={"mature_content_enabled": True}, headers=h
    )
    assert response.status_code == 403
    assert not settings_file.exists()
    assert get_settings().mature_content_enabled is False


@pytest.mark.parametrize("header", ["999999", "abc"])
def test_foreign_or_garbled_profile_header_is_rejected_not_degraded(
    client, as_user, accounts, settings_file, header
):
    """A write must never silently fall through to the global bucket because
    the lenient resolver dropped the header."""
    h = {**as_user(accounts["member"].id), "X-Profile-Id": header}
    response = client.put(
        "/settings", json={"mature_content_enabled": True}, headers=h
    )
    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"
    assert not settings_file.exists()


def test_foreign_profile_header_rejected_even_for_admin(
    client, as_user, accounts, settings_file
):
    other = str(accounts["member_profile"].id)  # not the admin's profile
    h = {**as_user(accounts["admin"].id), "X-Profile-Id": other}
    response = client.put(
        "/settings", json={"mature_content_enabled": True}, headers=h
    )
    assert response.status_code == 404
    assert not settings_file.exists()


def test_admin_without_header_writes_global_default(
    client, as_user, accounts, settings_file, db_session
):
    h = as_user(accounts["admin"].id)  # no header: explicit global write
    response = client.put(
        "/settings", json={"mature_content_enabled": True}, headers=h
    )
    assert response.status_code == 200, response.text
    assert json.loads(settings_file.read_text())["mature_content_enabled"] is True
    # Existing profiles keep their own toggle.
    profile = db_session.get(ReadingProfile, accounts["member_profile"].id)
    assert not profile.mature_content_enabled


# ---------------------------------------------------------------------------
# The scheduler honours `enabled` now
# ---------------------------------------------------------------------------


def test_scheduler_tick_skips_sweep_when_disabled(monkeypatch):
    from database.models import Base
    from database.session import SessionLocal, get_engine
    from services.update_scheduler import UpdateSchedulerManager
    from services.update_service import UpdateService

    # The manager reads the singleton row through SessionLocal, so give the
    # process engine a real schema (the autouse fixture already points it at a
    # scratch file).
    Base.metadata.create_all(get_engine())

    manager = UpdateSchedulerManager()
    triggered: list[str] = []
    monkeypatch.setattr(
        manager,
        "trigger_check",
        lambda *, trigger, tracker_ids=None: triggered.append(trigger) or True,
    )

    db = SessionLocal()
    try:
        service = UpdateService(db)
        row = service.get_global_settings()

        row.enabled = False
        db.commit()
        manager._tick()
        assert triggered == []  # disabled: the sweep really does not run

        row.enabled = True
        db.commit()
        manager._tick()
        assert triggered == ["scheduled"]
    finally:
        db.close()
