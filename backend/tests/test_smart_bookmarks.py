"""Smart bookmarks: exact position, object sync, both media (design 1g).

Four things are under test here, and they fail in four different ways:

1. **The merge.** Bookmarks are user-created objects, so the rules are an
   object store's, not progress' furthest-wins scalar. The headline case —
   a stale device replaying a create must NOT resurrect a bookmark deleted
   elsewhere — is exercised both as a pure function and end-to-end through
   the batch endpoint, because it is the failure the whole design exists to
   prevent.
2. **The position.** The anchor triple has to survive the round trip, land
   the same fraction of the chapter on any device, and degrade honestly when
   the content underneath it has changed.
3. **The listing.** The Bookmarks screen must be able to choose between
   bookmarks without a second round trip — which for novels means the
   sanitized text at that exact point, read from ``novel_chapter_cache`` and
   never fetched upstream.
4. **The scoping.** Profile isolation and the 18+ gate on every read and
   write. A cross-profile leak has shipped in this project before.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from core.errors import AppError
from core.time_utils import utcnow
from database.models import Bookmark, NovelChapterCache
from services.bookmark_service import (
    OP_DELETE,
    OP_UPSERT,
    STATUS_ALREADY_DELETED,
    STATUS_CREATED,
    STATUS_REJECTED_DELETED,
    STATUS_STALE,
    STATUS_TOMBSTONED,
    STATUS_UPDATED,
    BookmarkOp,
    BookmarkService,
    StoredState,
    clamp_fraction,
    decide,
    position_fraction,
    snippet_at,
    to_naive_utc,
)

SRC = "mangadex"
SERIES = "the-beginning-after-the-end"
NOVEL_SRC = "freewebnovel"
NOVEL_SERIES = "shadow-slave"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("bookmarker")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


@pytest.fixture
def api(app, client, acct):
    return client


def _svc(db_session, user_id, profile_id):
    return BookmarkService(db_session, user_id=user_id, profile_id=profile_id)


def _upsert(client_id: str, **over) -> dict:
    body = {
        "op": OP_UPSERT,
        "client_id": client_id,
        "source_id": SRC,
        "series_key": SERIES,
        "chapter_key": "c1",
        "chapter_number": 14.0,
        "media_type": "manga",
        "anchor_index": 4,
        "anchor_fraction": 0.5,
        "anchor_total": 10,
    }
    body.update(over)
    return body


def _delete(client_id: str, **over) -> dict:
    body = {"op": OP_DELETE, "client_id": client_id}
    body.update(over)
    return body


def _statuses(payload: dict) -> dict[str, str]:
    return {item["client_id"]: item["status"] for item in payload["items"]}


# ---------------------------------------------------------------------------
# 1. The merge, as a pure function
# ---------------------------------------------------------------------------


NOW = datetime(2026, 9, 5, 12, 0, 0)


def test_create_of_an_unseen_id_is_created():
    assert decide(None, BookmarkOp(op=OP_UPSERT, client_id="a"), now=NOW) == (
        STATUS_CREATED
    )


def test_upsert_against_a_tombstone_is_refused():
    """The rule the whole design exists for. Progress' merge would re-create."""
    stored = StoredState(deleted=True, updated_at=NOW)
    op = BookmarkOp(op=OP_UPSERT, client_id="a", updated_at=NOW + timedelta(days=7))
    assert decide(stored, op, now=NOW) == STATUS_REJECTED_DELETED


def test_a_tombstone_refuses_even_an_arbitrarily_newer_create():
    """Last-write-wins must not apply to a delete: a device offline for a year
    would otherwise win on the clock and undelete."""
    stored = StoredState(deleted=True, updated_at=NOW - timedelta(days=365))
    op = BookmarkOp(op=OP_UPSERT, client_id="a", updated_at=NOW)
    assert decide(stored, op, now=NOW) == STATUS_REJECTED_DELETED


def test_delete_of_an_unknown_id_still_tombstones():
    """Otherwise the race just inverts: the delete no-ops, then the create it
    was meant to cancel arrives and lands live."""
    assert decide(None, BookmarkOp(op=OP_DELETE, client_id="a"), now=NOW) == (
        STATUS_TOMBSTONED
    )


def test_delete_is_idempotent():
    stored = StoredState(deleted=True, updated_at=NOW)
    assert decide(stored, BookmarkOp(op=OP_DELETE, client_id="a"), now=NOW) == (
        STATUS_ALREADY_DELETED
    )


def test_delete_is_never_stale():
    """A delete carrying an old clock is still terminal — the alternative
    resurrects data."""
    stored = StoredState(deleted=False, updated_at=NOW)
    op = BookmarkOp(op=OP_DELETE, client_id="a", updated_at=NOW - timedelta(days=3))
    assert decide(stored, op, now=NOW) == STATUS_TOMBSTONED


def test_edits_to_a_live_bookmark_are_last_write_wins():
    stored = StoredState(deleted=False, updated_at=NOW)
    newer = BookmarkOp(op=OP_UPSERT, client_id="a", updated_at=NOW + timedelta(1))
    older = BookmarkOp(op=OP_UPSERT, client_id="a", updated_at=NOW - timedelta(1))
    tie = BookmarkOp(op=OP_UPSERT, client_id="a", updated_at=NOW)
    assert decide(stored, newer, now=NOW) == STATUS_UPDATED
    assert decide(stored, older, now=NOW) == STATUS_STALE
    # A tie goes to the stored row: two clocks that agree are not evidence of
    # a newer edit, and rewriting on equality makes the merge non-idempotent.
    assert decide(stored, tie, now=NOW) == STATUS_STALE


# ---------------------------------------------------------------------------
# 2. The merge, end to end through the batch endpoint
# ---------------------------------------------------------------------------


def test_replayed_create_does_not_resurrect_a_tombstoned_bookmark(api, h):
    """THE test (design §4).

    Device A creates a bookmark and deletes it. Device B, which has been
    offline since before the delete, later flushes its outbox — which still
    contains the create. The bookmark must stay deleted.
    """
    created = api.post(
        "/reader/bookmarks/batch", json=[_upsert("bm-1")], headers=h
    ).json()
    assert _statuses(created) == {"bm-1": STATUS_CREATED}

    deleted = api.post(
        "/reader/bookmarks/batch", json=[_delete("bm-1")], headers=h
    ).json()
    assert _statuses(deleted) == {"bm-1": STATUS_TOMBSTONED}
    assert api.get("/reader/bookmarks", headers=h).json() == []

    # Device B's stale outbox: the identical create, replayed, with a clock
    # newer than the delete for good measure.
    replay = api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("bm-1", updated_at="2099-01-01T00:00:00Z")],
        headers=h,
    )
    assert replay.status_code == 200, replay.text
    assert _statuses(replay.json()) == {"bm-1": STATUS_REJECTED_DELETED}
    assert replay.json()["rejected"] == 1
    assert replay.json()["created"] == 0

    # Still gone from the screen, and still a tombstone in the delta pull.
    assert api.get("/reader/bookmarks", headers=h).json() == []
    tombstones = api.get(
        "/reader/bookmarks", params={"include_deleted": "true"}, headers=h
    ).json()
    assert [(b["client_id"], b["deleted"]) for b in tombstones] == [("bm-1", True)]


def test_two_devices_creating_different_bookmarks_both_survive(api, h):
    """The other half of the merge: identity is the client's uuid, not the
    position, so concurrent creates never collide."""
    api.post("/reader/bookmarks/batch", json=[_upsert("dev-a")], headers=h)
    api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("dev-b", chapter_key="c2", anchor_index=7)],
        headers=h,
    )
    listed = api.get("/reader/bookmarks", headers=h).json()
    assert sorted(b["client_id"] for b in listed) == ["dev-a", "dev-b"]


def test_two_devices_can_bookmark_the_same_position_twice(api, h):
    """Same chapter, same page, two ids — two bookmarks. The position is not
    the identity, so this is not a conflict to resolve."""
    api.post("/reader/bookmarks/batch", json=[_upsert("one")], headers=h)
    api.post("/reader/bookmarks/batch", json=[_upsert("two")], headers=h)
    listed = api.get("/reader/bookmarks", headers=h).json()
    assert len(listed) == 2


def test_delete_arriving_before_the_create_still_wins(api, h):
    """Pre-emptive tombstone: B's delete is flushed before A's create ever
    reaches the server. Without a tombstone row the delete no-ops and the
    create then lands as a live bookmark both devices believe is gone."""
    early = api.post(
        "/reader/bookmarks/batch", json=[_delete("ghost")], headers=h
    ).json()
    assert _statuses(early) == {"ghost": STATUS_TOMBSTONED}

    late = api.post(
        "/reader/bookmarks/batch", json=[_upsert("ghost")], headers=h
    ).json()
    assert _statuses(late) == {"ghost": STATUS_REJECTED_DELETED}
    assert api.get("/reader/bookmarks", headers=h).json() == []


def test_create_then_delete_inside_one_batch_ends_deleted(api, h):
    """An outbox that recorded both must not depend on the flush being split
    across requests."""
    payload = api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("same"), _delete("same")],
        headers=h,
    ).json()
    assert [i["status"] for i in payload["items"]] == [
        STATUS_CREATED,
        STATUS_TOMBSTONED,
    ]
    assert api.get("/reader/bookmarks", headers=h).json() == []


def test_replaying_an_identical_batch_is_a_no_op(api, h):
    """Flushes are retried on flaky connections; the second one must not
    duplicate or bump anything."""
    first = api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("idem", updated_at="2026-09-05T10:00:00Z")],
        headers=h,
    ).json()
    second = api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("idem", updated_at="2026-09-05T10:00:00Z")],
        headers=h,
    ).json()
    assert _statuses(first) == {"idem": STATUS_CREATED}
    assert _statuses(second) == {"idem": STATUS_STALE}
    assert len(api.get("/reader/bookmarks", headers=h).json()) == 1


def test_a_later_edit_moves_the_bookmark_backwards(api, h):
    """Furthest-wins would be wrong here: dragging a bookmark back to an
    earlier page is a legitimate edit, not a rewind to discard."""
    api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("mv", anchor_index=9, updated_at="2026-09-05T10:00:00Z")],
        headers=h,
    )
    api.post(
        "/reader/bookmarks/batch",
        json=[
            _upsert(
                "mv",
                anchor_index=2,
                anchor_fraction=0.25,
                note="here instead",
                updated_at="2026-09-05T11:00:00Z",
            )
        ],
        headers=h,
    )
    (row,) = api.get("/reader/bookmarks", headers=h).json()
    assert (row["anchor_index"], row["anchor_fraction"]) == (2, 0.25)
    assert row["note"] == "here instead"


def test_tz_aware_client_clocks_are_normalized_not_crashed(api, h):
    """The columns are naive UTC; a client sends an offset. Comparing the two
    is a TypeError, so an ordinary ISO-8601 flush used to 500 mid-merge."""
    api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("tz", updated_at="2026-09-05T15:30:00+05:30")],
        headers=h,
    )
    # 15:30+05:30 == 10:00Z, so an 09:00Z edit is OLDER and must lose.
    older = api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("tz", note="no", updated_at="2026-09-05T09:00:00Z")],
        headers=h,
    ).json()
    assert _statuses(older) == {"tz": STATUS_STALE}
    newer = api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("tz", note="yes", updated_at="2026-09-05T11:00:00Z")],
        headers=h,
    ).json()
    assert _statuses(newer) == {"tz": STATUS_UPDATED}
    assert api.get("/reader/bookmarks", headers=h).json()[0]["note"] == "yes"


def test_to_naive_utc_converts_and_leaves_naive_alone():
    aware = datetime(2026, 9, 5, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert to_naive_utc(aware) == datetime(2026, 9, 5, 10, 0)
    naive = datetime(2026, 9, 5, 10, 0)
    assert to_naive_utc(naive) is naive
    assert to_naive_utc(None) is None


def test_one_malformed_item_does_not_wedge_the_flush(api, h):
    """A batch that 400s as a whole leaves the device retrying forever and
    never draining. The bad item is reported; the good ones land."""
    payload = api.post(
        "/reader/bookmarks/batch",
        json=[
            _upsert("good-1"),
            _upsert("bad", media_type="audiobook"),
            _upsert("good-2", chapter_key="c9"),
        ],
        headers=h,
    )
    assert payload.status_code == 200, payload.text
    body = payload.json()
    assert _statuses(body) == {
        "good-1": STATUS_CREATED,
        "bad": "invalid",
        "good-2": STATUS_CREATED,
    }
    assert [i["error"] for i in body["items"]] == [None, "invalid_media_type", None]
    assert sorted(
        b["client_id"] for b in api.get("/reader/bookmarks", headers=h).json()
    ) == ["good-1", "good-2"]


def test_batch_is_capped_like_the_progress_batch(api, h):
    from routes.reader import BOOKMARK_BATCH_MAX_ITEMS

    over = [_upsert(f"bm-{n}") for n in range(BOOKMARK_BATCH_MAX_ITEMS + 1)]
    resp = api.post("/reader/bookmarks/batch", json=over, headers=h)
    assert resp.status_code == 413
    body = resp.json()
    assert body["code"] == "batch_too_large"
    assert body["details"]["max_items"] == BOOKMARK_BATCH_MAX_ITEMS


def test_delete_of_an_unseen_id_records_the_body_it_was_given(api, h, db_session):
    """A pre-emptive tombstone keeps whatever identity the client could still
    supply, so a later listing of tombstones is not blank."""
    api.post(
        "/reader/bookmarks/batch",
        json=[_delete("pre", source_id=SRC, series_key=SERIES, chapter_key="c3")],
        headers=h,
    )
    row = db_session.query(Bookmark).filter_by(client_id="pre").one()
    assert (row.source_id, row.chapter_key) == (SRC, "c3")
    assert row.deleted_at is not None


# ---------------------------------------------------------------------------
# 3. Position: round trip, fraction, degradation
# ---------------------------------------------------------------------------


def test_single_post_round_trips_the_whole_anchor(api, h):
    created = api.post(
        "/reader/bookmark",
        json={
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_key": "c14",
            "chapter_number": 14.0,
            "media_type": "manga",
            "anchor_index": 9,
            "anchor_fraction": 0.375,
            "anchor_total": 15,
            "note": "the panel",
        },
        headers=h,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["anchor_index"] == 9
    assert body["anchor_fraction"] == 0.375
    assert body["anchor_total"] == 15
    assert body["chapter_number"] == 14.0
    assert body["media_type"] == "manga"
    # 8 whole pages + 0.375 of the ninth, out of 15.
    assert body["position_fraction"] == pytest.approx(0.5583, abs=1e-4)
    # A client that posted no id gets the server-minted one back, and needs it
    # to delete this bookmark through the offline batch later.
    assert body["client_id"]
    assert body["deleted"] is False


def test_a_client_supplied_id_is_kept(api, h):
    body = api.post(
        "/reader/bookmark",
        json={
            "client_id": "device-minted",
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_key": "c1",
        },
        headers=h,
    ).json()
    assert body["client_id"] == "device-minted"


def test_single_post_against_a_tombstone_is_a_409(api, h):
    """One deliberate user action: silently doing nothing would look like a
    working bookmark that vanishes on the next refresh."""
    api.post("/reader/bookmarks/batch", json=[_upsert("gone")], headers=h)
    api.post("/reader/bookmarks/batch", json=[_delete("gone")], headers=h)
    resp = api.post(
        "/reader/bookmark",
        json={
            "client_id": "gone",
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_key": "c1",
        },
        headers=h,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "bookmark_deleted"


def test_out_of_range_fractions_are_clamped_not_rejected(db_session, acct):
    """The service clamps rather than 400s: a client rounding 1.0000001 out of
    a scroll position must not have its bookmark refused forever."""
    uid, pid = acct
    svc = _svc(db_session, uid, pid)
    body = svc.add_bookmark(
        source_id=SRC,
        series_key=SERIES,
        chapter_key="c1",
        anchor_index=0,
        anchor_fraction=4.2,
        anchor_total=-3,
    )
    assert (body["anchor_index"], body["anchor_fraction"], body["anchor_total"]) == (
        1,
        1.0,
        0,
    )


@pytest.mark.parametrize(
    "value,expected",
    [(None, 0.0), (-1.0, 0.0), (0.5, 0.5), (2.0, 1.0), ("x", 0.0), (float("nan"), 0.0)],
)
def test_clamp_fraction(value, expected):
    assert clamp_fraction(value) == expected


def test_position_fraction_is_none_when_the_total_is_unknown():
    """Migrated page-only rows land here. "0% of the chapter" would be a
    fabrication — the client never told us how many pages there were."""
    assert position_fraction(4, 0.0, 0) is None


def test_position_fraction_clamps_a_shrunken_chapter():
    """Degrade honestly (design §3): a bookmark on page 9 of a chapter that
    now has 5 pages reports a position INSIDE the last page — halfway through
    page 5 of 5 — not 180%."""
    assert position_fraction(9, 0.5, 5) == 0.9
    assert position_fraction(9, 1.0, 5) == 1.0
    assert position_fraction(1, 0.0, 10) == 0.0


def test_the_deprecated_page_mirror_tracks_the_medium(api, h):
    """Shipped page-only clients keep rendering; a novel gets null, because a
    paragraph index is not a page."""
    manga = api.post(
        "/reader/bookmark",
        json={
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_key": "c1",
            "anchor_index": 6,
        },
        headers=h,
    ).json()
    novel = api.post(
        "/reader/bookmark",
        json={
            "source_id": NOVEL_SRC,
            "series_key": NOVEL_SERIES,
            "chapter_key": "n1",
            "media_type": "novel",
            "anchor_index": 6,
        },
        headers=h,
    ).json()
    assert manga["page"] == 6
    assert novel["page"] is None


def test_the_legacy_page_field_still_creates_a_bookmark(api, h):
    """The shipped web reader posts ``page``; it must land at the top of that
    page, exactly like the rows the migration carried forward."""
    body = api.post(
        "/reader/bookmark",
        json={
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_key": "c1",
            "page": 7,
        },
        headers=h,
    ).json()
    assert (body["anchor_index"], body["anchor_fraction"]) == (7, 0.0)


# ---------------------------------------------------------------------------
# 4. Listing enrichment: title, fraction, novel snippet
# ---------------------------------------------------------------------------


def _seed_novel_cache(db_session, paragraphs, *, chapter_key="n1"):
    row = NovelChapterCache(
        source_id=NOVEL_SRC,
        series_key=NOVEL_SERIES,
        chapter_key=chapter_key,
        title="Chapter One",
        chapter_number=1.0,
        paragraphs=json.dumps(paragraphs),
        word_count=sum(len(p.split()) for p in paragraphs),
        last_used_at=datetime(2020, 1, 1),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_listing_carries_everything_the_screen_needs(
    db_session, acct, seed_follow, seed_bookmark
):
    """Series title, chapter number and a position fraction — no second round
    trip to render "62% of chapter 14"."""
    uid, pid = acct
    seed_follow(uid, pid, source_id=SRC, series_key=SERIES, title="TBATE")
    seed_bookmark(
        uid,
        pid,
        source_id=SRC,
        series_key=SERIES,
        chapter_key="c14",
        chapter_number=14.0,
        anchor_index=7,
        anchor_fraction=0.2,
        anchor_total=11,
    )
    (row,) = _svc(db_session, uid, pid).list_bookmarks()
    assert row["series_title"] == "TBATE"
    assert row["chapter_number"] == 14.0
    assert row["position_fraction"] == pytest.approx(0.5636, abs=1e-4)
    assert row["snippet"] is None  # manga


def test_novel_listing_snippets_the_cached_text_at_that_position(
    db_session, acct, seed_bookmark
):
    uid, pid = acct
    paragraphs = [
        "The first paragraph, which the bookmark is not in.",
        "Sunny opened his eyes and the nightmare was still there, "
        "patient as ever, waiting at the foot of the bed for him to move.",
    ]
    _seed_novel_cache(db_session, paragraphs)
    seed_bookmark(
        uid,
        pid,
        source_id=NOVEL_SRC,
        series_key=NOVEL_SERIES,
        chapter_key="n1",
        media_type="novel",
        anchor_index=2,
        anchor_fraction=0.5,
        anchor_total=2,
    )
    (row,) = _svc(db_session, uid, pid).list_bookmarks()
    snippet = row["snippet"]
    assert snippet is not None
    # Starts AT the bookmarked point, not the paragraph's start, and says so.
    assert snippet.startswith("…")
    assert "nightmare" not in snippet
    assert "foot of the bed" in snippet
    assert row["anchor_stale"] is False


def test_listing_a_novel_bookmark_never_touches_the_cache_lru(db_session, acct, seed_bookmark):
    """Listing a bookmark is not reading the chapter. Bumping ``last_used_at``
    here would keep never-opened chapters alive at the expense of read ones."""
    uid, pid = acct
    cached = _seed_novel_cache(db_session, ["Only paragraph."])
    before = cached.last_used_at
    seed_bookmark(
        uid,
        pid,
        source_id=NOVEL_SRC,
        series_key=NOVEL_SERIES,
        chapter_key="n1",
        media_type="novel",
        anchor_index=1,
    )
    _svc(db_session, uid, pid).list_bookmarks()
    db_session.expire_all()
    assert db_session.get(
        NovelChapterCache, (NOVEL_SRC, NOVEL_SERIES, "n1")
    ).last_used_at == before


def test_a_novel_bookmark_with_no_cached_text_still_lists(
    db_session, acct, seed_bookmark
):
    """A cache miss means no snippet — never an upstream fetch, and never a
    missing row on the Bookmarks screen."""
    uid, pid = acct
    seed_bookmark(
        uid,
        pid,
        source_id=NOVEL_SRC,
        series_key=NOVEL_SERIES,
        chapter_key="uncached",
        media_type="novel",
        anchor_index=3,
        anchor_total=9,
    )
    (row,) = _svc(db_session, uid, pid).list_bookmarks()
    assert row["snippet"] is None
    assert row["position_fraction"] == pytest.approx(0.2222, abs=1e-4)


def test_snippet_degrades_to_the_nearest_paragraph_and_flags_it(
    db_session, acct, seed_bookmark
):
    """The chapter lost paragraphs since the bookmark was made. Land at the
    nearest valid position and say so, rather than failing or silently
    jumping to the top (design §3)."""
    uid, pid = acct
    _seed_novel_cache(db_session, ["Only one paragraph survives."])
    seed_bookmark(
        uid,
        pid,
        source_id=NOVEL_SRC,
        series_key=NOVEL_SERIES,
        chapter_key="n1",
        media_type="novel",
        anchor_index=12,
        anchor_total=20,
    )
    (row,) = _svc(db_session, uid, pid).list_bookmarks()
    assert row["anchor_stale"] is True
    assert "survives" in row["snippet"]


def test_snippet_at_snaps_to_a_word_boundary_and_truncates():
    text_para = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
    snippet, stale = snippet_at([text_para], 1, 0.4, max_chars=20)
    assert stale is False
    assert snippet.startswith("…")
    assert " " not in snippet[1:2]  # no leading orphan space
    assert snippet.endswith("…")


def test_snippet_at_on_an_empty_chapter_is_none():
    assert snippet_at([], 1, 0.0) == (None, False)


def test_listing_orders_newest_first_but_a_delta_pull_oldest_first(api, h):
    """A ``since`` pull pages forward on the last ``updated_at``; newest-first
    plus a limit would strand every change past the page boundary."""
    for n in range(3):
        api.post(
            "/reader/bookmarks/batch",
            json=[
                _upsert(
                    f"bm-{n}",
                    updated_at=f"2026-09-0{n + 1}T10:00:00Z",
                )
            ],
            headers=h,
        )
    screen = api.get("/reader/bookmarks", headers=h).json()
    assert [b["client_id"] for b in screen] == ["bm-2", "bm-1", "bm-0"]

    delta = api.get(
        "/reader/bookmarks",
        params={"since": "2026-09-01T00:00:00Z"},
        headers=h,
    ).json()
    assert [b["client_id"] for b in delta] == ["bm-0", "bm-1", "bm-2"]

    later = api.get(
        "/reader/bookmarks",
        params={"since": "2026-09-02T10:00:00Z"},
        headers=h,
    ).json()
    assert [b["client_id"] for b in later] == ["bm-2"]


def test_tombstones_are_only_visible_when_asked_for(api, h):
    api.post("/reader/bookmarks/batch", json=[_upsert("keep")], headers=h)
    api.post("/reader/bookmarks/batch", json=[_upsert("drop")], headers=h)
    api.post("/reader/bookmarks/batch", json=[_delete("drop")], headers=h)

    assert [b["client_id"] for b in api.get("/reader/bookmarks", headers=h).json()] == [
        "keep"
    ]
    with_dead = api.get(
        "/reader/bookmarks", params={"include_deleted": "true"}, headers=h
    ).json()
    assert sorted(b["client_id"] for b in with_dead) == ["drop", "keep"]
    assert {b["client_id"]: b["deleted"] for b in with_dead} == {
        "drop": True,
        "keep": False,
    }


def test_delete_by_row_id_tombstones_rather_than_removing(api, h, db_session):
    """The row has to stay, or an offline device never learns about the
    delete and its replayed create wins by default."""
    created = api.post(
        "/reader/bookmark",
        json={"source_id": SRC, "series_key": SERIES, "chapter_key": "c1"},
        headers=h,
    ).json()
    assert api.delete(f"/reader/bookmarks/{created['id']}", headers=h).status_code == (
        204
    )
    assert api.get("/reader/bookmarks", headers=h).json() == []
    # Deleting it again is a 404 — the listing already hides it.
    assert api.delete(f"/reader/bookmarks/{created['id']}", headers=h).status_code == (
        404
    )
    row = db_session.get(Bookmark, created["id"])
    db_session.refresh(row)
    assert row is not None and row.deleted_at is not None


def test_listing_filters_by_source_and_series(api, h):
    api.post("/reader/bookmarks/batch", json=[_upsert("a")], headers=h)
    api.post(
        "/reader/bookmarks/batch",
        json=[_upsert("b", series_key="other-series")],
        headers=h,
    )
    only = api.get(
        "/reader/bookmarks", params={"source": SRC, "series": SERIES}, headers=h
    ).json()
    assert [b["client_id"] for b in only] == ["a"]


# ---------------------------------------------------------------------------
# 5. Profile scoping + the 18+ gate
# ---------------------------------------------------------------------------


def test_batch_writes_land_in_the_active_profile_only(
    db_session, make_user, make_profile
):
    user = make_user("two-profiles")
    a = make_profile(user.id, "A")
    b = make_profile(user.id, "B")
    _svc(db_session, user.id, a.id).apply_batch(
        [
            BookmarkOp(
                op=OP_UPSERT,
                client_id="only-a",
                source_id=SRC,
                series_key=SERIES,
                chapter_key="c1",
            )
        ]
    )
    assert len(_svc(db_session, user.id, a.id).list_bookmarks()) == 1
    assert _svc(db_session, user.id, b.id).list_bookmarks() == []


def test_a_client_id_is_a_profile_namespace_not_a_global_one(
    db_session, make_user, make_profile
):
    """Two profiles colliding on a uuid is harmless, and the lookup that
    drives the merge is structurally unable to see the other profile's row."""
    user = make_user("colliding")
    a = make_profile(user.id, "A")
    b = make_profile(user.id, "B")
    for profile in (a, b):
        _svc(db_session, user.id, profile.id).apply_batch(
            [
                BookmarkOp(
                    op=OP_UPSERT,
                    client_id="same-uuid",
                    source_id=SRC,
                    series_key=SERIES,
                    chapter_key="c1",
                )
            ]
        )
    # Deleting in A must not tombstone B's.
    _svc(db_session, user.id, a.id).apply_batch(
        [BookmarkOp(op=OP_DELETE, client_id="same-uuid")]
    )
    assert _svc(db_session, user.id, a.id).list_bookmarks() == []
    assert len(_svc(db_session, user.id, b.id).list_bookmarks()) == 1


def test_another_profile_cannot_tombstone_by_guessing_a_row_id(
    db_session, make_user, make_profile, seed_bookmark
):
    user = make_user("guesser")
    a = make_profile(user.id, "A")
    b = make_profile(user.id, "B")
    row = seed_bookmark(user.id, a.id)
    with pytest.raises(AppError) as excinfo:
        _svc(db_session, user.id, b.id).delete_bookmark(row.id)
    assert excinfo.value.status_code == 404
    assert len(_svc(db_session, user.id, a.id).list_bookmarks()) == 1


def test_the_unscoped_bucket_cannot_write(db_session, make_user):
    user = make_user("no-profile")
    svc = _svc(db_session, user.id, None)
    with pytest.raises(AppError) as excinfo:
        svc.apply_batch([BookmarkOp(op=OP_UPSERT, client_id="x")])
    assert excinfo.value.code == "profile_required"
    assert excinfo.value.status_code == 400


def test_anonymous_reads_are_401(db_session):
    with pytest.raises(AppError) as excinfo:
        _svc(db_session, None, None).list_bookmarks()
    assert excinfo.value.status_code == 401


def _seed_mature(seed_follow, seed_bookmark, uid, pid, **over):
    seed_follow(
        uid,
        pid,
        source_id=SRC,
        series_key="adult-series",
        title="Adult Series",
        content_rating="adult",
    )
    return seed_bookmark(
        uid, pid, source_id=SRC, series_key="adult-series", **over
    )


def test_the_18plus_gate_hides_bookmarks_on_adult_series(
    db_session, make_user, make_profile, seed_follow, seed_bookmark
):
    user = make_user("gated")
    closed = make_profile(user.id, "Closed", mature_content_enabled=False)
    _seed_mature(seed_follow, seed_bookmark, user.id, closed.id)
    seed_bookmark(user.id, closed.id, source_id=SRC, series_key=SERIES)

    listed = _svc(db_session, user.id, closed.id).list_bookmarks()
    assert [b["series_key"] for b in listed] == [SERIES]


def test_the_18plus_gate_open_shows_them(
    db_session, make_user, make_profile, seed_follow, seed_bookmark
):
    user = make_user("ungated")
    open_profile = make_profile(user.id, "Open", mature_content_enabled=True)
    _seed_mature(seed_follow, seed_bookmark, user.id, open_profile.id)
    listed = _svc(db_session, user.id, open_profile.id).list_bookmarks()
    assert [b["series_key"] for b in listed] == ["adult-series"]
    assert listed[0]["series_title"] == "Adult Series"


def test_a_gated_write_applies_but_discloses_nothing(
    db_session, make_user, make_profile, seed_follow
):
    """Refusing the write would wedge an offline client retrying an op it can
    never flush. Accepting it discloses nothing: the row is the caller's own
    data, and the server-derived enrichment is withheld."""
    user = make_user("gated-writer")
    profile = make_profile(user.id, "Closed", mature_content_enabled=False)
    seed_follow(
        user.id,
        profile.id,
        source_id=SRC,
        series_key="adult-series",
        title="Adult Series",
        content_rating="adult",
    )
    svc = _svc(db_session, user.id, profile.id)
    body = svc.add_bookmark(
        source_id=SRC, series_key="adult-series", chapter_key="c1", anchor_index=2
    )
    assert body["anchor_index"] == 2
    assert body["series_title"] is None
    assert svc.list_bookmarks() == []


def test_the_gate_is_per_profile_not_per_account(
    db_session, make_user, make_profile, seed_follow, seed_bookmark
):
    """Profile "action" having 18+ off must not affect profile "porn"."""
    user = make_user("both")
    closed = make_profile(user.id, "Closed", mature_content_enabled=False)
    open_profile = make_profile(user.id, "Open", mature_content_enabled=True)
    for pid in (closed.id, open_profile.id):
        _seed_mature(seed_follow, seed_bookmark, user.id, pid)
    assert _svc(db_session, user.id, closed.id).list_bookmarks() == []
    assert len(_svc(db_session, user.id, open_profile.id).list_bookmarks()) == 1


def test_a_gated_novel_bookmark_leaks_no_snippet(
    db_session, make_user, make_profile, seed_follow
):
    """The snippet is chapter text; it must not come back in a write echo for
    a series the profile is not allowed to see."""
    user = make_user("gated-novel")
    profile = make_profile(user.id, "Closed", mature_content_enabled=False)
    seed_follow(
        user.id,
        profile.id,
        source_id=NOVEL_SRC,
        series_key=NOVEL_SERIES,
        title="Shadow Slave",
        content_rating="smut",
    )
    _seed_novel_cache(db_session, ["Explicit paragraph one.", "And two."])
    body = _svc(db_session, user.id, profile.id).add_bookmark(
        source_id=NOVEL_SRC,
        series_key=NOVEL_SERIES,
        chapter_key="n1",
        media_type="novel",
        anchor_index=1,
    )
    assert body["snippet"] is None
    assert body["series_title"] is None


# ---------------------------------------------------------------------------
# 6. Migration back-compat
# ---------------------------------------------------------------------------


def _alembic_config(db_path: Path):
    from alembic.config import Config

    import database.session as dbs

    backend_root = Path(dbs.__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.attributes["db_url"] = f"sqlite:///{db_path}"
    return cfg


def _legacy_db(db_path: Path, bookmark_values: str):
    """A database at the revision BEFORE this one, holding page-only bookmarks.

    Built by actually running Alembic to ``0009`` and inserting through raw
    SQL — the ORM models describe the POST-migration shape, so seeding through
    them would test the migration against itself. This is the thing that will
    happen on the VPS.
    """
    from alembic import command

    cfg = _alembic_config(db_path)
    command.upgrade(cfg, "0009_reading_session_duration")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, username, password_hash, is_admin, "
                "is_active, created_at, updated_at) VALUES "
                "(1, 'owner', 'x', 1, 1, '2026-01-01 00:00:00', "
                "'2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO reading_profiles (id, user_id, name, avatar_key, "
                "mood, sort_order, created_at) VALUES "
                "(1, 1, 'Main', 'default', 'neutral', 0, '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO bookmarks (id, user_id, profile_id, source_id, "
                "series_key, chapter_key, page, note, created_at) VALUES "
                + bookmark_values
            )
        )
    command.upgrade(cfg, "head")
    return engine


def test_existing_page_only_bookmarks_survive_the_upgrade(tmp_path):
    """Design §6: old page-only rows must resolve to offset 0.0 of that page."""
    engine = _legacy_db(
        tmp_path / "legacy.db",
        "(1, 1, 1, 'mangadex', 'series/one', 'ch/1', 4, 'a note', "
        "'2026-02-02 03:04:05'), "
        "(2, 1, 1, 'mangadex', 'series/one', 'ch/2', 1, NULL, "
        "'2026-02-03 03:04:05')",
    )

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT id, source_id, series_key, chapter_key, media_type, "
                    "anchor_index, anchor_fraction, anchor_total, chapter_number, "
                    "note, client_id, deleted_at, created_at, updated_at "
                    "FROM bookmarks ORDER BY id"
                )
            )
            .mappings()
            .all()
        )

    assert len(rows) == 2
    first, second = rows

    # The position is preserved, not converted: page 4 -> anchor_index 4, and
    # the fraction is the top of that page, which is what "page 4" meant.
    assert first["anchor_index"] == 4
    assert first["anchor_fraction"] == 0.0
    # The novel reader had no bookmark affordance before this revision, so
    # every pre-existing row is manga by construction.
    assert first["media_type"] == "manga"
    # Nobody recorded a page count, so the listing must say "unknown", not 0%.
    assert first["anchor_total"] == 0
    assert first["chapter_number"] is None
    # Identity survives untouched — keys keep their slashes, note keeps its text.
    assert (first["series_key"], first["chapter_key"]) == ("series/one", "ch/1")
    assert first["note"] == "a note"
    # Nothing is tombstoned by the migration.
    assert first["deleted_at"] is None and second["deleted_at"] is None
    # updated_at seeds from created_at, not now: a first delta pull must not
    # report every pre-existing bookmark as freshly changed.
    assert first["created_at"] == first["updated_at"]
    assert str(first["created_at"]).startswith("2026-02-02")
    # Every migrated row got a real, distinct uuid — not a placeholder, so
    # nothing downstream has to special-case a migrated bookmark.
    ids = {r["client_id"] for r in rows}
    assert len(ids) == 2
    assert all(len(cid) == 36 for cid in ids)

    assert second["anchor_index"] == 1


def test_the_upgrade_keeps_the_indexes_and_the_sync_uniqueness(tmp_path):
    """Dropping and rebuilding the table must leave the shape the queries
    assume: the delta-pull index, and the scoped uniqueness the merge's
    "does this id already exist?" lookup relies on."""
    engine = _legacy_db(
        tmp_path / "indexes.db",
        "(1, 1, 1, 'mangadex', 's1', 'c1', 2, NULL, '2026-02-02 03:04:05')",
    )
    with engine.connect() as conn:
        indexes = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='bookmarks'"
                )
            )
        }
    assert {
        "ix_bookmarks_user_id",
        "ix_bookmarks_profile_id",
        "ix_bookmarks_series",
        "ix_bookmarks_updated_at",
    } <= indexes

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO bookmarks (user_id, profile_id, client_id, "
                    "source_id, series_key, chapter_key, media_type, "
                    "anchor_index, anchor_fraction, anchor_total, created_at, "
                    "updated_at) SELECT user_id, profile_id, client_id, "
                    "source_id, series_key, chapter_key, media_type, "
                    "anchor_index, anchor_fraction, anchor_total, created_at, "
                    "updated_at FROM bookmarks WHERE id = 1"
                )
            )


def test_migrated_rows_are_readable_and_deletable_through_the_service(tmp_path):
    """A migrated row is not a second-class citizen: it lists with an honest
    unknown position and tombstones like any other."""
    from sqlalchemy.orm import sessionmaker

    engine = _legacy_db(
        tmp_path / "legacy2.db",
        "(1, 1, 1, 'mangadex', 's1', 'c1', 6, NULL, '2026-02-02 03:04:05')",
    )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        svc = BookmarkService(session, user_id=1, profile_id=1)
        (row,) = svc.list_bookmarks()
        assert row["anchor_index"] == 6
        assert row["anchor_fraction"] == 0.0
        assert row["position_fraction"] is None
        assert row["page"] == 6
        assert row["client_id"]

        svc.delete_bookmark(row["id"])
        assert svc.list_bookmarks() == []
        # And the tombstone refuses a replayed create for the migrated id.
        result = svc.apply_batch(
            [
                BookmarkOp(
                    op=OP_UPSERT,
                    client_id=row["client_id"],
                    source_id="mangadex",
                    series_key="s1",
                    chapter_key="c1",
                    updated_at=utcnow() + timedelta(days=1),
                )
            ]
        )
        assert result["items"][0]["status"] == STATUS_REJECTED_DELETED
    finally:
        session.close()


def test_the_downgrade_does_not_resurrect_deleted_bookmarks(tmp_path):
    """A downgrade is lossy by construction — the old table has nowhere to put
    a tombstone — so tombstoned rows are DROPPED, never revived. Reviving them
    is the exact failure the tombstone exists to prevent."""
    from alembic import command
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "downgrade.db"
    engine = _legacy_db(
        db_path,
        "(1, 1, 1, 'mangadex', 's1', 'c1', 6, NULL, '2026-02-02 03:04:05'), "
        "(2, 1, 1, 'mangadex', 's1', 'c2', 9, NULL, '2026-02-02 03:04:05')",
    )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        BookmarkService(session, user_id=1, profile_id=1).delete_bookmark(1)
    finally:
        session.close()
    engine.dispose()

    command.downgrade(_alembic_config(db_path), "0009_reading_session_duration")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, page FROM bookmarks ORDER BY id")
        ).all()
    assert rows == [(2, 9)]
