"""AUDIT VERIFY (shard mature-gate): does the 200 from POST /library/follow on a
hidden mature source leak that the source is adult (rating field) compared
with a source that does not exist?"""

from __future__ import annotations

import pytest

import connectors.registry as registry
from tests.test_audit_mature_library_writes import MATURE_SRC, StubMatureSource


@pytest.fixture
def stub():
    registry.register_connector(MATURE_SRC, StubMatureSource)
    yield
    registry._REGISTRY.pop(MATURE_SRC, None)
    registry._INSTANCE_CACHE.pop(MATURE_SRC, None)


def test_rating_field_on_follow_response(client, as_user, make_user, make_profile, stub):
    user = make_user("household")
    pid = make_profile(user.id, "Kid", mature_content_enabled=False).id
    h = as_user(user.id, pid)
    a = client.post("/library/follow", json={"source_id": MATURE_SRC, "series_key": "s1"}, headers=h).json()
    b = client.post("/library/follow", json={"source_id": "no_such_source_xyz", "series_key": "s1"}, headers=h).json()
    lst = client.get("/library/series", headers=h).json()
    items = lst if isinstance(lst, list) else lst.get("items", [])
    print("MATURE_RESP rating=", a.get("rating"), "content_rating=", a.get("content_rating"))
    print("UNKNOWN_RESP rating=", b.get("rating"), "content_rating=", b.get("content_rating"))
    print("KID_LIST sources=", [r.get("source_id") for r in items])
    assert a.get("rating") == b.get("rating"), "follow response distinguishes hidden-mature from nonexistent"
