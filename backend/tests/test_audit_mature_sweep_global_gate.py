"""AUDIT (shard mature-gate): the update sweep reads the gate from get_settings().

``UpdateService._check_one`` builds ``BrowseService(db=self._db)`` with no
``mature_enabled`` (update_service.py:501). ``BrowseService._gate_open`` then
falls back to ``get_settings().mature_content_enabled`` (browse_service.py:415),
which is False on the VPS (/data/settings.json is empty). ``_get_connector``
therefore 404s every adult source, so a series followed on one by a profile
whose OWN gate is open is never checked: ``last_error = "Source not found."``,
``known_chapters`` never refreshes, no notification is ever created.

The other half of the fix is asserted here too: once ``_check_one`` fetches
ungated, the *request*-scoped manual check has to refuse an id its own gate
hides, or a gated profile could drive a fetch it may not see the result of.
"""

from __future__ import annotations

import json

import pytest

import connectors.registry as registry
from connectors.base import SourceConnector
from connectors.models import BrowseMode, Chapter, PaginatedSeriesList, Series
from core import connector_directory
from core.config import get_settings
from core.errors import AppError
from database.models import UpdateNotification
from services.update_service import UpdateService

MATURE_SRC = "stub_mature_audit_sweep"
KEY = "s1"


class StubMatureSource(SourceConnector):
    SOURCE_TYPE = MATURE_SRC
    DISPLAY_NAME = "Stub Mature Sweep"
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
        return Series(id=series_id, title="Adult Series", chapter_count=2)

    def get_chapters(self, series_id):
        return [
            Chapter(id="c1", series_id=series_id, title="Ch 1", number=1.0, page_count=10),
            Chapter(id="c2", series_id=series_id, title="Ch 2", number=2.0, page_count=10),
        ]

    def get_chapter_pages(self, chapter_id):
        return []


@pytest.fixture
def stub_mature_source():
    # The memo is dropped on both edges: the rating rule reads the stub's
    # maturity through ``descriptor_for_source``, and a stale index answers
    # None for it -- which would silently switch off the source-is-adult rule
    # and pass the gate assertions below for the wrong reason.
    registry.register_connector(MATURE_SRC, StubMatureSource)
    connector_directory.reset_cache()
    yield
    registry._REGISTRY.pop(MATURE_SRC, None)
    registry._INSTANCE_CACHE.pop(MATURE_SRC, None)
    connector_directory.reset_cache()


def test_sweep_checks_an_adult_follow_of_an_open_profile(
    db_session, make_user, make_profile, seed_follow, stub_mature_source, monkeypatch
):
    monkeypatch.setattr(get_settings(), "mature_content_enabled", False)
    user = make_user("grown")
    profile = make_profile(user.id, "Grown", mature_content_enabled=True)
    follow = seed_follow(
        user.id, profile.id, source_id=MATURE_SRC, series_key=KEY,
        known_chapters=json.dumps([{"key": "c1", "number": 1, "title": "Ch 1"}]),
        notify=True,
    )
    settings = UpdateService(db_session, system=True).get_global_settings()
    settings.notify_enabled = True
    db_session.commit()

    run = UpdateService(db_session, system=True).run_check(trigger="manual", followed_ids=[follow.id])
    db_session.refresh(follow)

    assert follow.last_error is None, follow.last_error
    assert run["new_chapters_found"] == 1, run
    assert db_session.query(UpdateNotification).filter_by(followed_series_id=follow.id).count() == 1


def test_manual_check_refuses_a_follow_the_callers_own_gate_hides(
    db_session, make_user, make_profile, seed_follow, stub_mature_source
):
    """The sweep's ungated fetch must not become a way around the caller's gate.

    ``_check_one`` resolves its connector as a system actor now, so the only
    thing standing between a gated profile and a fetch of its own hidden 18+
    follow is ``resolve_followed_ids``. Addressed by id, a hidden follow is 404
    everywhere else (``followed_series_service.get_detail``); it is 404 here too.
    """
    user = make_user("minor")
    profile = make_profile(user.id, "Kid", mature_content_enabled=False)
    follow = seed_follow(user.id, profile.id, source_id=MATURE_SRC, series_key=KEY)

    service = UpdateService(db_session, user_id=user.id, profile_id=profile.id)
    with pytest.raises(AppError) as excinfo:
        service.check_followed_by_id(follow.id)

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "series_not_found"
    db_session.refresh(follow)
    assert follow.last_checked_at is None
    assert follow.known_chapters in (None, "[]")


def test_manual_check_runs_for_a_profile_whose_own_gate_is_open(
    db_session, make_user, make_profile, seed_follow, stub_mature_source, monkeypatch
):
    """The refusal above is the profile's gate, not a blanket ban on 18+ ids."""
    monkeypatch.setattr(get_settings(), "mature_content_enabled", False)
    user = make_user("grown2")
    profile = make_profile(user.id, "Grown", mature_content_enabled=True)
    follow = seed_follow(
        user.id, profile.id, source_id=MATURE_SRC, series_key=KEY,
        known_chapters=json.dumps([{"key": "c1", "number": 1, "title": "Ch 1"}]),
    )

    service = UpdateService(db_session, user_id=user.id, profile_id=profile.id)
    run = service.check_followed_by_id(follow.id)
    db_session.refresh(follow)

    assert follow.last_error is None, follow.last_error
    assert run["new_chapters_found"] == 1, run
