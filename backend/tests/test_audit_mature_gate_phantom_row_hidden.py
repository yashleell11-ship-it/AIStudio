"""AUDIT (shard mature-gate, MG-4 residue): a follow on a hidden mature source.

Written while the bug was open, when ``follow()`` swallowed ``ensure_visible``'s
404 and created a row the gated profile could then neither see nor manage --
rule 3 of ``resolve_tracker_rating`` rates any row on a mature *source* as
mature, so ``_visible``/``get_detail`` hid it. No content leaked; the residue
was a phantom row that still counted against the follow cap and was still swept
for updates.

Now that the follow itself is refused, this pins the closed shape: the refusal,
and the absence of any row behind it. Kept rather than deleted because the
phantom row is the part a future regression would leave behind quietly -- a
re-broken ``follow()`` would still answer 200 here, and still leave the row.
"""

from __future__ import annotations

import pytest

import connectors.registry as registry
from database.models import FollowedSeries
from tests.test_audit_mature_library_writes import MATURE_SRC, StubMatureSource


@pytest.fixture
def stub_mature_source():
    registry.register_connector(MATURE_SRC, StubMatureSource)
    yield
    registry._REGISTRY.pop(MATURE_SRC, None)
    registry._INSTANCE_CACHE.pop(MATURE_SRC, None)


def test_a_follow_on_a_hidden_source_leaves_no_phantom_row(
    client, as_user, make_user, make_profile, db_session, stub_mature_source
):
    user = make_user("household2")
    pid = make_profile(user.id, "Kid", mature_content_enabled=False).id
    headers = as_user(user.id, pid)

    resp = client.post(
        "/library/follow",
        json={"source_id": MATURE_SRC, "series_key": "s1"},
        headers=headers,
    )

    assert resp.status_code == 404, resp.json()
    assert (
        db_session.query(FollowedSeries)
        .filter_by(user_id=user.id, profile_id=pid, source_id=MATURE_SRC)
        .count()
        == 0
    ), "the refused follow still left a row behind"

    listing = client.get("/library/series", headers=headers)
    assert listing.status_code == 200
    payload = listing.json()
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    assert items == [] or all(r["source_id"] != MATURE_SRC for r in items)
