"""The 18+ gate over stored reading positions (spec §3.3, §4.1, §7).

``GET /reader/progress/series`` and ``GET /reader/history`` read
``chapter_progress``, which is correctly scoped to ``(user_id, profile_id)`` —
so nothing here is a cross-profile leak. They shipped with no maturity gate at
all, though, and that *is* a hole: a profile with the 18+ toggle shut still got
back its own stored positions for a mature series, ``source_id``,
``series_key``, ``chapter_key`` and ``chapter_number`` included, while browse,
the manifest, the Continue Reading strip, the Bookmarks screen and the
statistics screen all hid the same series from the same profile.

Every other read of ``chapter_progress`` was already gated
(``FollowedSeriesService.continue_reading``,
``ReadingStatsService._completed_count``); these two were the pair that was
missed. The tests below are the ones that would have caught it.

The write side is deliberately NOT gated — see
``test_a_gated_series_still_records_progress``.
"""

from __future__ import annotations

import pytest

import connectors.registry as registry
from connectors.base import SourceConnector
from connectors.models import BrowseMode, Chapter, PaginatedSeriesList, Page, Series
from core.errors import AppError
from services.progress_service import ProgressInput, ProgressService

SRC = "mangadex"
SAFE = "a-safe-series"
ADULT = "an-adult-series"

MATURE_SRC = "stub_mature_progress"
MATURE_SERIES = "gated-series/with-a/slash"


def _progress(db, user_id, profile_id):
    return ProgressService(db, user_id=user_id, profile_id=profile_id)


@pytest.fixture
def gated(make_user, make_profile):
    """One account, two profiles: 18+ on and 18+ off.

    Two profiles of the SAME account is the shape that matters. If any of this
    resolves its gate from ``get_settings()`` rather than from the request's
    profile — the bug that made the in-app toggle inert once before — both
    profiles answer identically and every assertion below passes for the wrong
    reason.
    """
    user = make_user("household")
    adult = make_profile(user.id, "Adult", mature_content_enabled=True)
    kid = make_profile(user.id, "Kid", mature_content_enabled=False, sort_order=1)
    return {"uid": user.id, "adult": adult.id, "kid": kid.id}


# --- GET /reader/progress/series -----------------------------------------


def test_series_progress_is_withheld_for_a_mature_series(
    db_session, gated, seed_follow, seed_progress
):
    """The reported hole, at the service.

    ``mature_override`` on a follow for ``mangadex`` — a general source no
    source-level gate ever touches, so the follow row's own rating is the only
    signal there is.
    """
    for pid in (gated["adult"], gated["kid"]):
        seed_follow(
            gated["uid"], pid, source_id=SRC, series_key=ADULT, mature_override=True
        )
        seed_progress(
            gated["uid"], pid, source_id=SRC, series_key=ADULT, chapter_key="c7",
            chapter_number=7.0, last_page=12,
        )

    allowed = _progress(db_session, gated["uid"], gated["adult"]).get_series_progress(
        SRC, ADULT
    )
    assert [r["chapter_key"] for r in allowed] == ["c7"]
    assert allowed[0]["last_page"] == 12

    withheld = _progress(db_session, gated["uid"], gated["kid"]).get_series_progress(
        SRC, ADULT
    )
    assert withheld == []


def test_series_progress_still_answers_for_a_safe_series(
    db_session, gated, seed_follow, seed_progress
):
    """The gate hides one series, not the profile's whole reader."""
    seed_follow(
        gated["uid"], gated["kid"], source_id=SRC, series_key=SAFE,
        mature_override=False,
    )
    seed_progress(
        gated["uid"], gated["kid"], source_id=SRC, series_key=SAFE, chapter_key="c1"
    )

    rows = _progress(db_session, gated["uid"], gated["kid"]).get_series_progress(
        SRC, SAFE
    )
    assert [r["chapter_key"] for r in rows] == ["c1"]


def test_series_progress_keeps_an_unfollowed_series_visible(
    db_session, gated, seed_progress
):
    """Unfollowing is not a rating.

    With no follow row there is no rating signal beyond the source's own, and
    ``resolve_tracker_rating`` deliberately does not fold unknown into mature —
    otherwise a gated profile would lose the history of every series it ever
    stopped following. Pins the join as an OUTER one; an inner join (which is
    what ``continue_reading`` correctly uses, because a *strip of the library*
    is follow-scoped by definition) would drop this row.
    """
    seed_progress(
        gated["uid"], gated["kid"], source_id=SRC, series_key="drive-by",
        chapter_key="c1",
    )
    rows = _progress(db_session, gated["uid"], gated["kid"]).get_series_progress(
        SRC, "drive-by"
    )
    assert [r["chapter_key"] for r in rows] == ["c1"]


# --- GET /reader/history -------------------------------------------------


def test_history_omits_the_profiles_own_mature_series(
    db_session, gated, seed_follow, seed_progress
):
    """One layer up, the same defect: a shut gate still listed its own 18+ rows."""
    for key, mature in ((SAFE, False), (ADULT, True)):
        seed_follow(
            gated["uid"], gated["kid"], source_id=SRC, series_key=key,
            mature_override=mature,
        )
        seed_progress(
            gated["uid"], gated["kid"], source_id=SRC, series_key=key,
            chapter_key=f"{key}-c1",
        )

    history = _progress(db_session, gated["uid"], gated["kid"]).reading_history()
    assert [r["series_key"] for r in history] == [SAFE]


def test_history_shows_the_same_rows_to_a_profile_with_the_gate_open(
    db_session, gated, seed_follow, seed_progress
):
    """The gate is the only thing doing the hiding — nothing is lost."""
    seed_follow(
        gated["uid"], gated["adult"], source_id=SRC, series_key=ADULT,
        mature_override=True,
    )
    seed_progress(
        gated["uid"], gated["adult"], source_id=SRC, series_key=ADULT,
        chapter_key="c1",
    )

    history = _progress(db_session, gated["uid"], gated["adult"]).reading_history()
    assert [r["series_key"] for r in history] == [ADULT]


def test_history_hides_progress_on_a_mature_source_with_no_follow_row(
    db_session, gated, seed_progress, stub_mature_source
):
    """The source's own maturity is the fall-through when no follow row exists.

    ``reading_history`` spans sources, so it cannot call ``ensure_visible``
    (that raises, and one deregistered source in the history would take the
    whole list down with it). The source gate therefore has to be part of the
    rating resolution, exactly as it is for bookmarks and the statistics screen.
    """
    seed_progress(
        gated["uid"], gated["kid"], source_id=MATURE_SRC, series_key=MATURE_SERIES,
        chapter_key="c1",
    )
    seed_progress(
        gated["uid"], gated["kid"], source_id=SRC, series_key=SAFE, chapter_key="c1"
    )

    history = _progress(db_session, gated["uid"], gated["kid"]).reading_history()
    assert [r["source_id"] for r in history] == [SRC]


def test_history_pages_over_the_rows_the_caller_can_actually_see(
    db_session, gated, seed_follow, seed_progress
):
    """The gate has to run in SQL, before ``limit``/``offset``.

    Filtering the page in Python afterwards hands back short pages — ask for
    two and get one — and a client paging on ``offset`` then steps over the
    rows the filter removed, so the tail of a gated profile's history simply
    disappears. Interleaved so a post-hoc filter cannot pass by luck.
    """
    from core.time_utils import utcnow

    base = utcnow()
    for n in range(6):
        key = ADULT if n % 2 else SAFE
        seed_follow(
            gated["uid"], gated["kid"], source_id=SRC, series_key=f"{key}-{n}",
            mature_override=bool(n % 2),
        )
        seed_progress(
            gated["uid"], gated["kid"], source_id=SRC, series_key=f"{key}-{n}",
            chapter_key="c1",
            # Descending, so the newest row is n=0 and the ordering is defined.
            last_read_at=base.replace(microsecond=n),
        )

    svc = _progress(db_session, gated["uid"], gated["kid"])
    page1 = svc.reading_history(limit=2, offset=0)
    page2 = svc.reading_history(limit=2, offset=2)
    assert len(page1) == 2
    assert [r["series_key"] for r in page1 + page2] == [
        f"{SAFE}-4", f"{SAFE}-2", f"{SAFE}-0"
    ]


# --- the write side ------------------------------------------------------


def test_a_gated_series_still_records_progress(
    db_session, gated, seed_follow, seed_progress
):
    """Hiding is not forgetting — the write stays ungated, on purpose.

    A household profile switching the 18+ toggle off is asking not to be shown
    adult series; it is not asking the server to stop remembering where the
    account got to. Gating the write would silently drop pushes a client keeps
    retrying from its offline outbox, and flipping the toggle back on would
    reveal a series stranded at whatever page it held when the toggle flipped.
    The same call is what ``BookmarkService`` makes for the same reason: the
    write applies, and the gate applies to the read of it.
    """
    seed_follow(
        gated["uid"], gated["kid"], source_id=SRC, series_key=ADULT,
        mature_override=True,
    )
    svc = _progress(db_session, gated["uid"], gated["kid"])
    saved = svc.save_one(
        ProgressInput(
            source_id=SRC, series_key=ADULT, chapter_key="c9", chapter_number=9.0,
            last_page=4,
        )
    )
    assert saved["advanced"] is True

    # Stored, and invisible to the profile that stored it...
    assert svc.get_series_progress(SRC, ADULT) == []
    # ...until the gate opens.
    reopened = _progress(db_session, gated["uid"], gated["adult"])
    seed_follow(
        gated["uid"], gated["adult"], source_id=SRC, series_key=ADULT,
        mature_override=True,
    )
    seed_progress(
        gated["uid"], gated["adult"], source_id=SRC, series_key=ADULT,
        chapter_key="c9", chapter_number=9.0, last_page=4,
    )
    assert [r["last_page"] for r in reopened.get_series_progress(SRC, ADULT)] == [4]


# --- the source gate, over the real wiring -------------------------------


class StubMatureProgressSource(SourceConnector):
    """A MATURE source in the real registry — no network, no fixtures.

    Nothing here is ever asked for content; it exists so ``get_browse_service``
    has a genuinely 18+ source to gate, which is what turns "the progress routes
    inherit the caller's gate" into something a test can observe end to end.
    """

    SOURCE_TYPE = MATURE_SRC
    DISPLAY_NAME = "Stub Mature Progress"
    DESCRIPTION = "Test-only mature source."
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True
    CONTENT_KIND = "manga"

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    def list_browse_modes(self) -> list[BrowseMode]:
        return [BrowseMode(id="default", label="Browse")]

    def get_series_list(self, page: int, *, sort: str | None = None):
        return PaginatedSeriesList(items=[], page=page, page_size=20, total=0)

    def search_series(self, query: str, page: int, *, sort: str | None = None):
        return self.get_series_list(page, sort=sort)

    def get_series(self, series_id: str) -> Series | None:
        return None

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return []

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return []


@pytest.fixture
def stub_mature_source():
    registry.register_connector(MATURE_SRC, StubMatureProgressSource)
    yield
    registry._REGISTRY.pop(MATURE_SRC, None)
    registry._INSTANCE_CACHE.pop(MATURE_SRC, None)


def test_series_progress_answers_a_mature_source_exactly_as_the_manifest_does(
    db_session, gated, seed_progress, stub_mature_source
):
    """404 ``source_not_found``, byte-identical to browse and the manifest.

    ``GET /reader/chapter/manifest`` already 404s this source for this profile.
    A route in the same file, called by the same screen, that answers with the
    profile's stored positions instead is the asymmetry this fixes — and 404,
    never 403: off-limits is indistinguishable from absent.
    """
    seed_progress(
        gated["uid"], gated["kid"], source_id=MATURE_SRC, series_key=MATURE_SERIES,
        chapter_key="c1",
    )
    with pytest.raises(AppError) as err:
        _progress(db_session, gated["uid"], gated["kid"]).get_series_progress(
            MATURE_SRC, MATURE_SERIES
        )
    assert err.value.status_code == 404
    assert err.value.code == "source_not_found"

    seed_progress(
        gated["uid"], gated["adult"], source_id=MATURE_SRC,
        series_key=MATURE_SERIES, chapter_key="c1",
    )
    allowed = _progress(db_session, gated["uid"], gated["adult"]).get_series_progress(
        MATURE_SRC, MATURE_SERIES
    )
    assert [r["chapter_key"] for r in allowed] == ["c1"]


# --- end to end ----------------------------------------------------------


def test_both_routes_gate_on_the_requests_profile_not_a_global_setting(
    client, as_user, gated, seed_follow, seed_progress
):
    """Same account, same token, same rows — only ``X-Profile-Id`` differs."""
    for pid in (gated["adult"], gated["kid"]):
        seed_follow(
            gated["uid"], pid, source_id=SRC, series_key=ADULT, mature_override=True
        )
        seed_progress(
            gated["uid"], pid, source_id=SRC, series_key=ADULT, chapter_key="c3"
        )

    params = {"source": SRC, "series": ADULT}
    adult_h = as_user(gated["uid"], gated["adult"])
    kid_h = as_user(gated["uid"], gated["kid"])

    allowed = client.get("/reader/progress/series", params=params, headers=adult_h)
    assert allowed.status_code == 200, allowed.text
    assert [r["chapter_key"] for r in allowed.json()] == ["c3"]
    assert client.get("/reader/history", headers=adult_h).json() != []

    withheld = client.get("/reader/progress/series", params=params, headers=kid_h)
    assert withheld.status_code == 200, withheld.text
    assert withheld.json() == []
    assert client.get("/reader/history", headers=kid_h).json() == []


def test_the_gated_routes_are_still_shut_to_an_anonymous_caller(client, gated):
    """Auth first: the gate is not what is keeping strangers out."""
    assert client.get(
        "/reader/progress/series", params={"source": SRC, "series": SAFE}
    ).status_code == 401
    assert client.get("/reader/history").status_code == 401
