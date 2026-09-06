"""AUDIT (shard mature-gate): the unscoped bucket and new-profile seed read the
instance-global ``Settings.mature_content_enabled``.

These tests assert the *safe* behaviour the finding proposes, so they FAIL on
the current tree iff the finding is real:

* an authenticated account that owns a profile with 18+ OFF, sending a request
  with NO ``X-Profile-Id`` (lenient resolver -> profile_id=None,
  core/profile_context.py:96-109) must NOT see an adult source when the global
  default is True (core/content_rating.py:102-106 falls back to the global);
* a profile created without an explicit toggle must NOT start with 18+ ON just
  because the global is True (services/profile_service.py:155-162).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from connectors.models import Series as ConnectorSeries
from core.config import get_settings
from core.content_rating import resolve_mature_gate
from services.profile_service import ProfileService
from tests.test_sources_search import (
    _FakeConnector,
    _FakeDescriptor,
    _make_list_installed,
)

SAFE = "safe-src"
MATURE = "mature-src"


def _search(client, headers):
    descriptors = [
        _FakeDescriptor(SAFE, name="Safe Source"),
        _FakeDescriptor(MATURE, name="Adult Source", mature=True),
    ]
    connectors = {
        SAFE: _FakeConnector([ConnectorSeries(id="s-1", title="Lookism")]),
        MATURE: _FakeConnector([ConnectorSeries(id="m-1", title="Lookism After Dark")]),
    }
    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch(
        "services.browse_service.create_connector",
        side_effect=lambda source_id: connectors[source_id],
    ):
        return client.get("/sources/search", params={"q": "lookism"}, headers=headers).json()


@pytest.fixture
def global_gate_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "mature_content_enabled", True)
    yield


def test_headerless_request_from_closed_profile_account_hides_adult_source(
    client, as_user, make_user, make_profile, global_gate_on
):
    user = make_user("prude")
    make_profile(user.id, "SFW", mature_content_enabled=False)

    payload = _search(client, as_user(user.id))  # no X-Profile-Id

    sources = {g["source"] for g in payload["groups"]}
    assert MATURE not in sources, (
        "dropping X-Profile-Id opened the 18+ gate via the global default"
    )


def test_resolve_mature_gate_unscoped_authenticated_is_closed(
    db_session, make_user, global_gate_on
):
    user = make_user("someone")
    assert resolve_mature_gate(db_session, None, user.id) is False


def test_new_profile_does_not_seed_from_global(db_session, make_user, global_gate_on):
    user = make_user("newbie")
    profile = ProfileService(db_session, user_id=user.id).create_profile(name="Fresh")
    assert bool(profile.mature_content_enabled) is False
