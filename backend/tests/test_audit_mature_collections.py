"""AUDIT (shard mature-gate): collections are the one library read with no gate.

``GET /library/collections/{id}`` lists every ``(source_id, series_key)`` in
the collection and ``GET /library/collections`` prints a ``series_count`` —
neither consults the profile's 18+ gate (``followed_series_service.py``
``get_collection`` / ``list_collections``). A member series on an adult
source (its id alone is the disclosure: "nhentai") or a followed series the
profile itself marked ``mature_override`` is hidden on every other surface
and printed here.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, update

from database.models import Collection, CollectionSeries, ReadingProfile

SRC = "mangadex"
ADULT = "an-adult-series"
SAFE = "a-safe-series"
MATURE_SRC = "nhentai"  # a real registered adult source; no network involved


@pytest.fixture
def kid(make_user, make_profile):
    user = make_user("household")
    return {"uid": user.id, "pid": make_profile(user.id, "Kid", mature_content_enabled=False).id}


@pytest.fixture
def collection(db_session, kid, seed_follow):
    seed_follow(kid["uid"], kid["pid"], source_id=SRC, series_key=ADULT, mature_override=True)
    seed_follow(kid["uid"], kid["pid"], source_id=SRC, series_key=SAFE, mature_override=False)
    row = Collection(user_id=kid["uid"], profile_id=kid["pid"], name="Mixed")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    for i, (src, key) in enumerate(((SRC, SAFE), (SRC, ADULT), (MATURE_SRC, "12345"))):
        db_session.add(
            CollectionSeries(collection_id=row.id, source_id=src, series_key=key, sort_order=i)
        )
    db_session.commit()
    return row.id


def test_collection_detail_hides_gated_members(client, as_user, kid, collection):
    headers = as_user(kid["uid"], kid["pid"])
    # Sanity: the library itself hides the adult follow for this profile.
    listed = {r["series_key"] for r in client.get("/library/series", headers=headers).json()["items"]}
    assert listed == {SAFE}

    body = client.get(f"/library/collections/{collection}", headers=headers).json()
    members = {(s["source_id"], s["series_key"]) for s in body["series"]}
    assert members == {(SRC, SAFE)}, members


def test_collection_listing_count_excludes_gated_members(client, as_user, kid, collection):
    headers = as_user(kid["uid"], kid["pid"])
    body = client.get("/library/collections", headers=headers).json()
    assert body[0]["series_count"] == 1, body


def _members(db_session, collection_id: int) -> set[tuple[str, str]]:
    # A count/select against the engine, not the identity map: the app commits
    # in its own session and ``session_factory`` mirrors production's
    # ``expire_on_commit=False``, so a ``Session.get`` here could answer from
    # the objects the fixture added rather than from what the route left behind.
    rows = db_session.execute(
        select(CollectionSeries.source_id, CollectionSeries.series_key).where(
            CollectionSeries.collection_id == collection_id
        )
    ).all()
    return {(r.source_id, r.series_key) for r in rows}


def _remove(client, headers, collection_id: int, src: str, key: str):
    return client.request(
        "DELETE",
        f"/library/collections/{collection_id}/series",
        json={"source_id": src, "series_key": key},
        headers=headers,
    )


def test_remove_of_a_gated_member_is_indistinguishable_from_an_absent_one(
    client, as_user, kid, collection, db_session
):
    """The write must answer exactly as it does for a member that was never
    added — same status, nothing deleted. A 404 for hidden where absent gives
    204 would let a gated profile probe a collection for adult members."""
    headers = as_user(kid["uid"], kid["pid"])
    before = _members(db_session, collection)
    absent = _remove(client, headers, collection, SRC, "never-added")

    for src, key in ((SRC, ADULT), (MATURE_SRC, "12345")):
        resp = _remove(client, headers, collection, src, key)
        assert resp.status_code == absent.status_code == 204, (src, key, resp.text)
        assert _members(db_session, collection) == before, (src, key)

    # The visible member is still removable by the same profile.
    assert _remove(client, headers, collection, SRC, SAFE).status_code == 204
    assert _members(db_session, collection) == before - {(SRC, SAFE)}


def test_remove_of_a_gated_member_works_once_the_gate_is_open(
    client, as_user, kid, collection, db_session
):
    # The collection belongs to this profile, so it is this profile's own
    # gate that has to open — a sibling with 18+ on cannot address it at all.
    db_session.execute(
        update(ReadingProfile)
        .where(ReadingProfile.id == kid["pid"])
        .values(mature_content_enabled=True)
    )
    db_session.commit()
    headers = as_user(kid["uid"], kid["pid"])
    assert _remove(client, headers, collection, SRC, ADULT).status_code == 204
    assert (SRC, ADULT) not in _members(db_session, collection)
