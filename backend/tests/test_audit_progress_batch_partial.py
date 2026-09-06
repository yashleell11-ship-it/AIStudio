"""AUDIT (shard outboxes, server half): a progress batch is per-item.

``POST /reader/progress/batch`` used to validate its array as one unit, so a
single unparseable row made the whole flush a 422. The phone drains its outbox
oldest-first and clears rows only on a 2xx, so that row wedged every later push
behind it for ever. The batch now lands what it can parse and reports the rest
by its index in the array the client sent.

These pin the response contract the clients read; the wedge itself is pinned by
``test_audit_outbox_replay.test_progress_batch_with_one_bad_item_still_lands_the_good_ones``.
"""

from __future__ import annotations

import pytest

SRC = "mangadex"
SERIES = "solo-leveling"


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("batch-partial")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


def _push(chapter: int, **kw) -> dict:
    item = {
        "source_id": SRC,
        "series_key": SERIES,
        "chapter_key": f"ch-{chapter}",
        "chapter_number": float(chapter),
        "last_page": 7,
        "page_count": 20,
    }
    item.update(kw)
    return item


def test_rejected_items_are_reported_by_their_index_in_the_request(client, h):
    """The index is the only handle the client has: nothing else on the wire
    identifies a push, so a report the device cannot map back to an outbox row
    is a report it can only ignore."""
    body = [_push(1, last_page=0), _push(2), _push(3, source_id="")]
    r = client.post("/reader/progress/batch", json=body, headers=h)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["saved"] == 1
    assert [item["chapter_key"] for item in payload["items"]] == ["ch-2"]
    assert [bad["index"] for bad in payload["rejected"]] == [0, 2]
    # Enough to debug the offending row without echoing it back.
    assert payload["rejected"][0]["errors"][0]["field"] == "last_page"
    assert payload["rejected"][0]["errors"][0]["message"]


def test_a_wholly_unparseable_batch_is_still_a_200_the_client_can_clear(client, h):
    """A 4xx here means the device keeps the rows and re-sends them; the point
    of the change is that a row the server will never accept stops being
    permanent. ``saved`` of 0 with every index reported says exactly that."""
    body = [_push(1, last_page=0), "not an object", None]
    r = client.post("/reader/progress/batch", json=body, headers=h)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["saved"] == 0
    assert payload["items"] == []
    assert [bad["index"] for bad in payload["rejected"]] == [0, 1, 2]


def test_a_clean_batch_reports_nothing_rejected(client, h):
    r = client.post("/reader/progress/batch", json=[_push(1), _push(2)], headers=h)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["saved"] == 2
    assert payload["rejected"] == []


def test_the_batch_cap_stays_fatal(client, h):
    """The 413 is not a per-item problem: the client obeys it by sending fewer
    items, so softening it would only hide the bound."""
    from routes.reader import PROGRESS_BATCH_MAX_ITEMS

    body = [_push(n) for n in range(PROGRESS_BATCH_MAX_ITEMS + 1)]
    r = client.post("/reader/progress/batch", json=body, headers=h)

    assert r.status_code == 413
    assert r.json()["code"] == "batch_too_large"
