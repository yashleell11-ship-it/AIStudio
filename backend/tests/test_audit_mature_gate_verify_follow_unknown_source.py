"""AUDIT VERIFY (shard mature-gate): does POST /library/follow accept a source
id that does not exist at all (not merely a hidden mature one)? If so the
finder's bug is a special case of "follow never validates source_id"."""

from __future__ import annotations

from database.models import FollowedSeries


def test_follow_accepts_a_source_that_does_not_exist(client, as_user, make_user, make_profile, db_session):
    user = make_user("household")
    pid = make_profile(user.id, "Kid", mature_content_enabled=False).id
    headers = as_user(user.id, pid)
    assert client.get("/sources/no_such_source_xyz/browse-modes", headers=headers).status_code == 404
    resp = client.post(
        "/library/follow", json={"source_id": "no_such_source_xyz", "series_key": "s1"}, headers=headers
    )
    rows = db_session.query(FollowedSeries).filter_by(source_id="no_such_source_xyz").all()
    print("STATUS", resp.status_code, "ROWS", len(rows), "BODY", resp.json())
    # Same shape as the hidden-mature case: is the row created and visible in the list?
    lst = client.get("/library/series", headers=headers)
    print("LIST", lst.status_code, [r.get("source_id") for r in (lst.json() if isinstance(lst.json(), list) else lst.json().get("items", []))])
    assert resp.status_code == 404, "follow accepted an unknown source"
