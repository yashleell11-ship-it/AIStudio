"""``GET /sources/search`` honours the per-profile 18+ gate (spec §5.3).

Restores the coverage that was lost with ``LibraryIntelligenceService``. The
gate now lives in ``routes/sources.py`` ``federated_search`` — it passes
``include_mature=service._gate_open()``, and ``_gate_open`` resolves the active
profile's ``mature_content_enabled`` via ``core.content_rating.resolve_mature_gate``
(wired in ``get_browse_service``).

A mature source's results must be hidden for a profile with the gate closed and
shown when it is open.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from connectors.models import Series as ConnectorSeries
from tests.test_sources_search import (
    _FakeConnector,
    _FakeDescriptor,
    _make_list_installed,
)

SAFE = "safe-src"
MATURE = "mature-src"


@pytest.fixture
def api(app, client):
    return client


def _search(api, headers):
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
        return api.get("/sources/search", params={"q": "lookism"}, headers=headers).json()


def test_mature_source_hidden_when_profile_gate_is_closed(
    api, as_user, make_user, make_profile
):
    user = make_user("prude")
    profile = make_profile(user.id, "SFW", mature_content_enabled=False)

    payload = _search(api, as_user(user.id, profile.id))

    sources = {g["source"] for g in payload["groups"]}
    assert MATURE not in sources
    assert SAFE in sources
    assert payload["sources_queried"] == 1
    assert all(item["source"] != MATURE for item in payload["items"])


def test_mature_source_shown_when_profile_gate_is_open(
    api, as_user, make_user, make_profile
):
    user = make_user("adult")
    profile = make_profile(user.id, "NSFW", mature_content_enabled=True)

    payload = _search(api, as_user(user.id, profile.id))

    sources = {g["source"] for g in payload["groups"]}
    assert {SAFE, MATURE} <= sources
    assert payload["sources_queried"] == 2
    assert "Lookism After Dark" in {item["title"] for item in payload["items"]}
