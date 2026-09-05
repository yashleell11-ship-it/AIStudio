"""The 18+ rating rule has exactly ONE implementation, and each surface names
only the column it applies that rule to.

``tests/test_mature_gate_cross_surface.py`` next door proves the surfaces
*agree* right now, through the router, for one series. This file pins the
structural reason they cannot stop agreeing.

The rule shipped as five hand-copied SQL expressions across four services --
``reading_stats`` twice (reading sessions, chapter progress), ``bookmark``,
``progress`` and ``update`` -- each written by a different change closing the
same authorisation hole. Every copy was byte-for-byte the same CASE except for
which table's ``source_id`` it read. That is the drift risk the cross-surface
test cannot catch on its own: a gap fixed in one copy leaves four unfixed, all
five files stay green, and the failure is silent -- a series correctly hidden on
four screens and printed by name on the fifth, which is precisely the bug the
gate was introduced to remove.

The copies are now delegators to
:func:`core.content_rating.mature_tracker_case`, beside the
``resolve_tracker_rating`` it mirrors. These assert that and nothing more.

Deliberately NOT asserted here: the *join* that supplies the ``followed_series``
row. Those differ on purpose and are documented at each call site -- outer
against a composite key for sessions, bookmarks and history, a foreign-key
equality for notifications, applied unconditionally for bookmarks and only when
the gate is shut for sessions and notifications. Consolidating those would erase
deliberate differences; only the rating rule is shared.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.dialects import sqlite

from core.content_rating import mature_tracker_case
from database.models import (
    Bookmark,
    ChapterProgress,
    ReadingSession,
    UpdateNotification,
)
from services.bookmark_service import BookmarkService
from services.progress_service import ProgressService
from services.reading_stats_service import ReadingStatsService
from services.update_service import UpdateService

BACKEND = Path(__file__).resolve().parents[1]

#: (surface, the service's gate predicate, the column it must be resolving).
#: The predicates are read off the class and called with ``self=None`` because
#: the rule is a pure function of that one column -- if one of them ever needs
#: instance state again it has stopped being the shared rule, and the
#: ``TypeError`` here is the intended alarm.
GATES = [
    ("statistics/sessions", ReadingStatsService._mature_case, ReadingSession.source_id),
    (
        "statistics/completed",
        ReadingStatsService._progress_mature_case,
        ChapterProgress.source_id,
    ),
    ("bookmarks", BookmarkService._mature_case, Bookmark.source_id),
    ("reader/history", ProgressService._mature_case, ChapterProgress.source_id),
    ("updates/notifications", UpdateService._mature_case, UpdateNotification.source_id),
]


def _sql(expression) -> str:
    """The expression as literal SQLite SQL — what the database actually sees."""
    return str(
        expression.compile(
            dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.parametrize(
    "gate, column", [(g, c) for _, g, c in GATES], ids=[s for s, _, _ in GATES]
)
def test_every_gated_surface_emits_the_shared_rule(gate, column):
    assert _sql(gate(None)) == _sql(mature_tracker_case(column))


def test_the_source_column_is_what_distinguishes_the_surfaces():
    """Guard against the parametrised test above passing vacuously.

    If ``_sql`` did not render the source column, every comparison above would
    hold no matter which table a surface gated on — including a service gating
    ``chapter_progress`` rows against ``bookmarks.source_id``.
    """
    assert _sql(mature_tracker_case(ReadingSession.source_id)) != _sql(
        mature_tracker_case(Bookmark.source_id)
    )


def test_only_content_rating_spells_the_rule_out():
    """A sixth copy would have to write the override branch again. None may.

    Cheap and blunt on purpose: the five copies were introduced by three agents
    who each reasonably copied the nearest working version, and a source scan is
    what catches the fourth one doing the same.
    """
    home = BACKEND / "core" / "content_rating.py"
    offenders = sorted(
        str(path.relative_to(BACKEND))
        for path in BACKEND.rglob("*.py")
        if ".venv" not in path.parts
        and "tests" not in path.parts
        and path != home
        and "mature_override == 1" in path.read_text(encoding="utf-8")
    )
    assert offenders == [], (
        "the 18+ rating rule is spelled out outside core/content_rating.py; "
        "call mature_tracker_case(<table>.source_id) instead"
    )
