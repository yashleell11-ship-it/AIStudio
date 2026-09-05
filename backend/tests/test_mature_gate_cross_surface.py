"""One series, one profile, every gated read surface — they must agree.

The 18+ gate over stored rows was closed one surface at a time, by three
separate changes: ``update_service`` (notifications), ``progress_service``
(``/reader/progress/series`` + ``/reader/history``), ``source_cache_service``
(the series cache), on top of ``bookmark_service`` and ``ocr_ingest_service``
before them. Each shipped with its own test file, and each of those files
proves only that *its own* surface hides the series.

That is the gap this file covers. Nothing pinned that the surfaces agree with
each other, and they resolve the rating through three different mechanisms —
a SQL ``_mature_case`` mirror (history, bookmarks, notifications), a Python
``resolve_tracker_rating`` call (``progress/series``), and
``BrowseService.ensure_visible`` (the source-level check). Three mirrors of one
rule drift silently: a change to any one of them keeps every existing file
green while the screens start disagreeing about what is adult, which is exactly
the inconsistency the gate existed to remove — hidden in browse, listed in
history.

So these assert the whole surface at once, through the router, with the profile
as the only variable:

  * a shut gate hides the series **everywhere** (not on three of four screens);
  * an open gate shows it **everywhere** — the regression that "fixing" a leak
    by breaking the feature would produce, and the one no denial test can catch;
  * a shut gate hides nothing that is not adult.
"""

from __future__ import annotations

import pytest

from database.models import UpdateNotification

SRC = "mangadex"
ADULT = "an-adult-series"
SAFE = "a-safe-series"


@pytest.fixture
def household(make_user, make_profile):
    """One account, two profiles. The gate is the only difference between them.

    Two profiles of the same account is the shape that matters: anything that
    resolves its gate from ``get_settings()`` rather than from the request's
    profile answers identically for both, and every assertion below would pass
    for the wrong reason.
    """
    user = make_user("household")
    return {
        "uid": user.id,
        "kid": make_profile(user.id, "Kid", mature_content_enabled=False).id,
        "grown": make_profile(
            user.id, "Grown", mature_content_enabled=True, sort_order=1
        ).id,
    }


@pytest.fixture
def seeded(db_session, household, seed_follow, seed_progress, seed_bookmark):
    """The identical two series under both profiles, on every gated surface.

    ``mature_override`` on a ``mangadex`` follow deliberately: a general source
    no source-level check ever touches, so the follow row's own rating is the
    only signal there is and every surface has to resolve it the same way.
    """
    for pid in (household["kid"], household["grown"]):
        for series_key, adult in ((ADULT, True), (SAFE, False)):
            follow = seed_follow(
                household["uid"], pid, source_id=SRC, series_key=series_key,
                mature_override=adult,
            )
            seed_progress(
                household["uid"], pid, source_id=SRC, series_key=series_key,
                chapter_key="c1",
            )
            seed_bookmark(
                household["uid"], pid, source_id=SRC, series_key=series_key,
                chapter_key="c1",
            )
            db_session.add(
                UpdateNotification(
                    user_id=household["uid"],
                    profile_id=pid,
                    followed_series_id=follow.id,
                    source_id=SRC,
                    series_key=series_key,
                    chapter_key="c1",
                    chapter_title="Chapter 1",
                    chapter_number=1.0,
                    is_read=False,
                )
            )
    db_session.commit()


def _surfaces(client, headers) -> dict[str, object]:
    """Every gated read of a stored row, as the client actually calls them."""
    return {
        "progress/series": [
            r["chapter_key"]
            for r in client.get(
                "/reader/progress/series",
                params={"source": SRC, "series": ADULT},
                headers=headers,
            ).json()
        ],
        "history": sorted(
            r["series_key"]
            for r in client.get("/reader/history", headers=headers).json()
        ),
        "bookmarks": sorted(
            r["series_key"]
            for r in client.get("/reader/bookmarks", headers=headers).json()
        ),
        "notifications": sorted(
            n["series_key"]
            for n in client.get("/updates/notifications", headers=headers).json()
        ),
        "badge": client.get(
            "/updates/notifications/unread-count", headers=headers
        ).json()["count"],
    }


def test_a_shut_gate_hides_the_same_series_on_every_surface(
    client, as_user, household, seeded
):
    """Hidden in browse means hidden in *all* of the profile's own records.

    A gate that holds on three screens and not the fourth is what the original
    defect was; asserting the surfaces together is what keeps the three separate
    mirrors of the rating rule from drifting apart one commit at a time.
    """
    got = _surfaces(client, as_user(household["uid"], household["kid"]))

    assert got["progress/series"] == []
    assert got["history"] == [SAFE]
    assert got["bookmarks"] == [SAFE]
    assert got["notifications"] == [SAFE]
    # The badge has to count exactly the listing, or the client shows an unread
    # number for something it can never open and that never falls.
    assert got["badge"] == 1


def test_an_open_gate_shows_the_same_series_on_every_surface(
    client, as_user, household, seeded
):
    """The ordinary case, which no denial test can catch.

    Same account, same rows, same tokens — only ``X-Profile-Id`` differs. It is
    easy to close a leak by breaking the feature, and a profile that opted in to
    adult content must still get its own reading position, history, bookmarks
    and new-chapter notifications for a mature series.
    """
    got = _surfaces(client, as_user(household["uid"], household["grown"]))

    both = sorted([ADULT, SAFE])
    assert got["progress/series"] == ["c1"]
    assert got["history"] == both
    assert got["bookmarks"] == both
    assert got["notifications"] == both
    assert got["badge"] == 2


def test_the_history_total_header_counts_what_the_body_returns(
    client, as_user, household, seeded
):
    """The count the client is handed is the count of what it was handed.

    ``/reader/history`` reports the page's own cardinality, so this is not a
    claim about a table total. It pins the header to the *gated* page: the gate
    lives inside the query, and a filter moved out of SQL to a pass over the
    rows afterwards would keep the body correct while the header went on
    reporting the ungated count.
    """
    for profile, expected in (("kid", 1), ("grown", 2)):
        resp = client.get(
            "/reader/history", headers=as_user(household["uid"], household[profile])
        )
        assert len(resp.json()) == expected
        assert resp.headers["X-Total-Count"] == str(expected)
