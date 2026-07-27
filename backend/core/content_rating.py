"""Shared definition of what counts as mature (18+) content, and the single
place that answers "is the 18+ gate open for this caller right now?".

Everything that gates adult content goes through this module. That is
deliberate: the gate previously lived in two unconnected places -- a global
``Settings.mature_content_enabled`` read by the browse layer and a per-profile
``ReadingProfile.mature_content_enabled`` written by the clients -- so flipping
the switch in the app changed the value the app read back and nothing else.
One resolution path (:func:`resolve_mature_gate`) and one rating rule
(:func:`is_mature_rating` / :func:`mature_rating_predicate`) is what keeps those
two halves from drifting apart again.

Three things are gated, by three different signals:

- whole *sources* that are adult by nature (``SourceConnector.is_mature`` /
  ``ConnectorDescriptor.mature``);
- local *series* by their stored ``Series.content_rating``; and
- *followed remote series* by :func:`resolve_tracker_rating`, since a tracker
  has no local series row to read a rating off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import get_settings
from database.models import ReadingProfile

if TYPE_CHECKING:  # pragma: no cover - typing only
    from connectors.registry import ConnectorDescriptor
    from database.models import SeriesTracker

#: Series ``content_rating`` values (compared case-insensitively) that denote
#: adult / 18+ content. Mirrors common source vocabularies -- e.g. MangaDex
#: uses "erotica" and "pornographic".
MATURE_CONTENT_RATINGS: frozenset[str] = frozenset(
    {
        "pornographic",
        "erotica",
        "smut",
        "hentai",
        "adult",
        "mature",
        "nsfw",
        "18+",
        "r18",
        "r-18",
    }
)

#: Resolved maturity of a followed remote series. ``"unknown"`` is a real third
#: state, not a synonym for either of the others -- see
#: :func:`resolve_tracker_rating`.
TRACKER_RATING_MATURE = "mature"
TRACKER_RATING_SAFE = "safe"
TRACKER_RATING_UNKNOWN = "unknown"


def is_mature_rating(content_rating: str | None) -> bool:
    """Whether a series ``content_rating`` denotes adult (18+) content."""
    if not content_rating:
        return False
    return content_rating.strip().lower() in MATURE_CONTENT_RATINGS


def mature_rating_predicate(column):
    """SQL mirror of :func:`is_mature_rating`: TRUE when ``column`` is adult.

    ``trim`` is applied because the Python rule strips whitespace and the SQL
    rule used not to, so a stored ``" adult"`` was mature in one layer and safe
    in the other. ``coalesce`` is applied because ``IN`` against NULL evaluates
    to NULL, and a ``NOT IN`` filter therefore *dropped* unrated rows instead of
    keeping them -- the opposite of what an unrated row should do (see
    :func:`resolve_tracker_rating` on why unknown is not treated as adult).
    """
    normalized = func.lower(func.trim(func.coalesce(column, "")))
    return normalized.in_(sorted(MATURE_CONTENT_RATINGS))


def resolve_mature_gate(
    db: Session,
    profile_id: int | None,
    user_id: int | None = None,
) -> bool:
    """Is adult content allowed for this (user, profile) right now?

    The active profile's own toggle wins; the global config value is only the
    fallback for the unscoped/legacy bucket (and the seed for new profiles).
    Every gated read path resolves the gate here so profile "action" having 18+
    off can never affect profile "porn".

    ``user_id`` is optional only because the callers that predate it already
    pass a ProfileContext-validated id. Pass it whenever you have it: this
    function is deliberately the single resolution path and will attract new
    callers, and one that forwards a raw header would otherwise read another
    account's gate. A mismatch falls back to the global default rather than
    honouring the foreign profile.
    """
    if profile_id is not None:
        profile = db.get(ReadingProfile, profile_id)
        if profile is not None and (user_id is None or profile.user_id == user_id):
            return bool(profile.mature_content_enabled)
    return get_settings().mature_content_enabled


def resolve_tracker_rating(
    tracker: SeriesTracker,
    descriptor: ConnectorDescriptor | None,
) -> str:
    """Maturity of a *followed remote* series, resolved in priority order.

    A tracker has no local ``Series`` row to read ``content_rating`` off
    (``SeriesTracker.local_series_id`` is never written), and
    ``connectors.models.Series`` carries no rating field, so the rating has to
    be assembled from what is actually available:

    1. ``mature_override`` -- the user said so explicitly. Wins over everything,
       and is the only signal that works for the many dead connectors where no
       metadata will ever arrive again.
    2. ``content_rating`` captured at follow time from the connector's genres.
    3. The *source's* own maturity: a tracker on an 18+ source is 18+ by
       construction. Free to evaluate, needs no network, and this is where the
       owner's adult content actually comes from (toonily, nhentai, hentai20…).
    4. Otherwise unknown.

    Where the signal is ambiguous we err towards hiding: a *hint* of adult
    content in rule 2 (any genre matching MATURE_CONTENT_RATINGS) is enough, and
    rule 3 condemns the whole source rather than asking for per-series proof --
    the failure the owner cares about is 18+ content appearing where he did not
    expect it, so a false hide (one tap on "not 18+") costs far less than a
    false show.

    Unknown is deliberately NOT folded into mature, and that is the one place
    this module does not err towards hiding. ``Series.content_rating`` defaults
    to the literal string ``"unknown"`` and nothing populates it on folder
    import, so unknown-as-adult would blank the owner's entire library the first
    time he turned the gate off -- he would turn it back on permanently and the
    gate would protect nothing at all. Unknown is instead surfaced *and marked*
    (serialized as ``rating: "unknown"``) so the client can badge it and offer
    the one-tap override that writes rule 1.
    """
    if tracker.mature_override is not None:
        return TRACKER_RATING_MATURE if tracker.mature_override else TRACKER_RATING_SAFE
    if tracker.content_rating:
        return (
            TRACKER_RATING_MATURE
            if is_mature_rating(tracker.content_rating)
            else TRACKER_RATING_SAFE
        )
    if descriptor is not None and descriptor.mature:
        return TRACKER_RATING_MATURE
    return TRACKER_RATING_UNKNOWN


def rating_from_genres(genres: tuple[str, ...] | list[str] | None) -> str | None:
    """Derive a stored ``content_rating`` from a connector's genre tuple.

    Madara-family sites routinely tag adult works "Adult", "Mature" or "Smut"
    and expose nothing else machine-readable, so a genre hit is the only rating
    signal available at follow time. Returns the matched vocabulary term (so the
    stored value round-trips through :func:`is_mature_rating`) or ``None`` when
    nothing matched -- ``None`` means "no signal", which resolves to unknown
    rather than to safe.
    """
    for genre in genres or ():
        normalized = (genre or "").strip().lower()
        if normalized in MATURE_CONTENT_RATINGS:
            return normalized
    return None
