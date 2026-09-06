"""Data-layer audit, shard "outboxes" — the server half.

The phone's progress outbox (``ProgressOutboxController`` in
``mobile/lib/features/downloads/providers/progress_outbox_provider.dart``)
relies on ``POST /reader/progress/batch`` being safe to replay: its doc comment
says "the server's furthest-wins merge makes a replayed push harmless, so
there is no 'flushed twice' failure mode to guard against", and the store
comment says "a crash between a successful POST and this row's deletion
self-heals on the next flush".

That is true for the position and false for ``time_spent_seconds``, which the
merge ACCUMULATES (``merge_progress``: ``stored + incoming``). The phone
re-sends a row whenever a flush overlaps another flush (there is no
single-flight guard) or the app dies between the 200 and the local DELETE.
Every replay adds the delta again.

These tests encode the contract the client believes it has. They are
EXPECTED TO FAIL on the current code; that failure is the finding.
"""

from __future__ import annotations

import pytest

SRC = "mangadex"
SERIES = "solo-leveling"


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("outbox-replay")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


def _push(chapter: int, *, last_page: int = 7, time_spent: int = 30) -> dict:
    return {
        "source_id": SRC,
        "series_key": SERIES,
        "chapter_key": f"ch-{chapter}",
        "chapter_number": float(chapter),
        "last_page": last_page,
        "page_count": 20,
        "is_completed": False,
        "time_spent_seconds": time_spent,
        # Stamped on the device at capture time, exactly as the outbox does —
        # the replay carries the SAME stamp, so the server could tell.
        "last_read_at": "2026-09-01T12:00:00Z",
    }


def _stored(client, h, chapter: int) -> dict:
    r = client.get(
        "/reader/progress/series",
        params={"source": SRC, "series": SERIES},
        headers=h,
    )
    assert r.status_code == 200, r.text
    rows = [row for row in r.json() if row["chapter_key"] == f"ch-{chapter}"]
    assert rows, "the chapter should have a progress row"
    return rows[0]


def test_replaying_the_same_batch_is_idempotent_for_time_spent(client, h):
    """A row the phone flushed twice (overlapping flushes, or a kill between
    the 200 and the DELETE) must not be counted twice.

    FAILS today: the second identical batch adds another 30 s, so the stored
    reading time is 60 s for 30 s of reading.
    """
    body = [_push(1)]
    first = client.post("/reader/progress/batch", json=body, headers=h)
    assert first.status_code == 200, first.text
    assert _stored(client, h, 1)["time_spent_seconds"] == 30

    replay = client.post("/reader/progress/batch", json=body, headers=h)
    assert replay.status_code == 200, replay.text
    # Position is unchanged (advanced == 0) — the merge DID recognise the
    # replay as a no-op for the position...
    assert replay.json()["advanced"] == 0
    # ...but not for the delta it carries.
    assert _stored(client, h, 1)["time_spent_seconds"] == 30, (
        "replayed push was accumulated again — time_spent_seconds is a delta "
        "with no idempotency key, so every outbox re-send inflates it"
    )


def test_progress_batch_with_one_bad_item_still_lands_the_good_ones(client, h):
    """The bookmark batch (``sync_bookmarks_batch``) documents why a whole-
    batch refusal is wrong for an offline outbox: "a flush that 400s as a whole
    leaves the device unable to make progress at all". The progress batch does
    not apply that rule — ``body: list[ProgressRequest]`` is validated as one
    unit, so one unsendable row (here ``last_page: 0``) makes the phone re-send
    the identical 422 batch on every launch, resume and page turn forever,
    and nothing queued behind it is ever saved.

    FAILS today: 422 and no row for ch-1.
    """
    body = [_push(1), _push(2, last_page=0)]
    r = client.post("/reader/progress/batch", json=body, headers=h)
    assert r.status_code == 200, (
        f"whole batch refused ({r.status_code}); the phone keeps every row and "
        "retries the same refusal indefinitely"
    )
    assert _stored(client, h, 1)["last_page"] == 7
