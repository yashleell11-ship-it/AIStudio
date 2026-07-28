"""Object-level read authorization for a local series and everything under it.

This is the single place that answers "may this caller read series S at all?".
Listing scope (``LibraryService.list_series``' INNER JOIN on membership) already
decided what shows up in a grid; it never guarded a *fetch by id*, so any
authenticated household member could resolve any series, chapter, page image or
cover by guessing a numeric id. This module closes that, and lives in ``core/``
rather than on either service because ``LibraryService`` and
``LibraryIntelligenceService`` already carry duplicated membership helpers to
dodge an import cycle (see ``library_intelligence_service._library_on``) — a
duplicated *authorization* rule is the one that must never be allowed to drift.

The rule
--------

    readable(series S, caller account U) ⇔ any of
        user_series_state row for (S, U)          -- added / downloaded / imported
     OR reading_progress   row for (S, U)          -- read it, never added it
     OR bookmarks          row for (S, U)          -- bookmarked it, never added it
     OR S sits in a collection owned by U          -- collected it, never added it
     OR user_series_state row for (S, user_id IS NULL)   -- claimed by nobody

Three deliberate choices, each of which would break a legitimate read if made
the other way:

**ACCOUNT-level, not profile-level.** ``profile_id`` is absent on purpose. One
household shares one filesystem and one catalog; a profile is a persona, not a
security boundary. Scoping reads to the profile would deny a sibling profile
opening a series the account downloaded, deny every profile on a legacy download
whose ``profile_id`` is NULL, deny a pre-profiles library (``AuthService.
_claim_unowned_data`` sets ``user_id`` and leaves ``profile_id`` NULL), and deny
*every* read made while no ``X-Profile-Id`` header is set — which both clients do
routinely during boot and mid-profile-switch (``resolve_profile_context`` is
lenient and yields ``profile_id=None``). Child safety is the 18+ gate's job:
that gate IS per-profile, is applied separately by each caller here, and is not
replaced by this predicate.

**Presence of the row, not ``in_library``.** ``in_library`` is the *shelf* bit
(``models.UserSeriesState.in_library``). A row legitimately exists with it false
after favouriting from Browse, after setting a reading status from Browse, and
after ``set_in_library(False)`` — which keeps the row on purpose so progress and
favourites survive a remove-and-re-add. Authorizing on the shelf bit would 404
the series the Continue Reading strip is at that moment advertising.

**``user_id`` NULL is SCOPED, never EXEMPT.** A caller with ``user_id is None``
(the unscoped/legacy bucket: background workers, and the test suite's in-memory
admin) matches the ``IS NULL`` rows and nothing else. There is deliberately no
``if user_id is None: return True`` branch — that would look like a passing suite
while proving nothing, and would hand a bypass to any future request path that
loses its context.

The last arm is the counterpart on the *row* side: a series whose only claim is
an owner-less row is claimed by nobody. That is the ambiguous case, and it is
resolved towards allowing the read. Such rows are only ever created by callers
that have no request context at all (a download whose ``Download.user_id`` is
NULL because it predates ownership, or an auto-download queued before
``update_auto_download`` learned to stamp the tracker's owner) — no authenticated
request can produce one, because every route sits behind ``enforce_authentication``
and ``_get_or_create_state`` stamps the caller. Treating that content as readable
matches what the product already does with unowned data elsewhere:
``AuthService._claim_unowned_data`` hands all of it to the household owner. The
alternative — content that arrived on this instance being readable by no one at
all — is the failure mode this change exists to avoid.

Note what this does NOT claim to be: the catalog is deliberately household-shared
and ``POST /library/series/{id}/add`` lets any account claim any catalog series,
so this enforces *"you must have claimed it"*, not content ownership. It closes
the silent read; true per-account content ownership would need an owner column on
``series`` and is a separate decision.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database.models import (
    Bookmark,
    Collection,
    CollectionSeries,
    ReadingProgress,
    UserSeriesState,
)


def series_read_allowed(db: Session, user_id: int | None, series_id: int) -> bool:
    """Whether ``user_id``'s account has any claim on ``series_id``.

    Returns a bool rather than raising so each call site can fail with *its own*
    existing not-found error (``series_not_found`` / ``chapter_not_found`` /
    ``page_not_found``). A denial must be indistinguishable from the object never
    having existed: a distinct "exists but not yours" code — or a 403 — would
    confirm the id, which is itself the disclosure.

    One round trip. Every arm is a covered EXISTS: ``ix_user_series_state_series``
    + ``uq_user_series_state``, ``ix_reading_progress_series_id`` +
    ``uq_reading_progress_user_series``, ``ix_bookmarks_series_id``,
    ``ix_collection_series_series_id`` + ``ix_collections_user_id``. SQL ORs
    short-circuit, so the common case (the caller owns the series) stops at the
    first arm.
    """
    claims = (
        select(UserSeriesState.id)
        .where(
            UserSeriesState.series_id == series_id,
            UserSeriesState.user_id == user_id,
        )
        .exists(),
        select(ReadingProgress.id)
        .where(
            ReadingProgress.series_id == series_id,
            ReadingProgress.user_id == user_id,
        )
        .exists(),
        select(Bookmark.id)
        .where(
            Bookmark.series_id == series_id,
            Bookmark.user_id == user_id,
        )
        .exists(),
        select(CollectionSeries.series_id)
        .join(Collection, Collection.id == CollectionSeries.collection_id)
        .where(
            CollectionSeries.series_id == series_id,
            Collection.user_id == user_id,
        )
        .exists(),
        select(UserSeriesState.id)
        .where(
            UserSeriesState.series_id == series_id,
            UserSeriesState.user_id.is_(None),
        )
        .exists(),
    )
    return bool(db.execute(select(or_(*claims))).scalar())
