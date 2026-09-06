"""AUDIT (concurrency CONC-3): the loser of a first-push race must MERGE.

``tests/test_audit_concurrency_progress_first_push_race.py`` proves the two
concurrent pushes both return 2xx. This is the other half of the claim: what
the loser's push does to the row the winner created. It must be exactly what it
would have done had its own SELECT run a moment later — furthest-wins, no
rewind, its reading time credited once — rather than being dropped on the floor
in the name of not raising.

The interleaving is reproduced deterministically: read (nothing there), let the
other connection commit its insert, then apply.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from core.time_utils import utcnow
from database.models import ChapterProgress, ReadingSession
from services.progress_service import ProgressInput, ProgressService

SRC = "mangadex"
SERIES = "solo-leveling"
CHAPTER = "ch-1"


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("race-merge")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


def _push(**kw) -> ProgressInput:
    base = dict(
        source_id=SRC,
        series_key=SERIES,
        chapter_key=CHAPTER,
        chapter_number=1.0,
        page_count=20,
    )
    base.update(kw)
    return ProgressInput(**base)


def test_the_loser_of_a_first_push_race_merges_onto_the_winners_row(
    session_factory, db_session, acct
):
    uid, pid = acct
    now = utcnow()
    slow = ProgressService(session_factory(), user_id=uid, profile_id=pid)
    quick = ProgressService(session_factory(), user_id=uid, profile_id=pid)

    behind = _push(last_page=3, time_spent_seconds=60, last_read_at=now)
    # The slow request reads first and finds nothing...
    prefetched = slow._prefetch([behind])  # noqa: SLF001
    assert prefetched == {}
    # ...the quick one inserts the chapter's first row in the meantime...
    quick.save_one(_push(last_page=9, last_read_at=now - timedelta(minutes=1)))
    # ...and only then does the slow one write.
    slow._apply_one(behind, prefetched=prefetched)  # noqa: SLF001
    slow._db.commit()  # noqa: SLF001

    rows = db_session.query(ChapterProgress).filter_by(user_id=uid).all()
    assert len(rows) == 1, "the race inserted the chapter twice"
    assert rows[0].last_page == 9, "the loser's behind-push rewound the reader"
    # The loser's push still counted: its clock is newer than the row's, so its
    # delta is a read rather than a replay.
    assert rows[0].time_spent_seconds == 60
    sessions = db_session.query(ReadingSession).filter_by(user_id=uid).all()
    assert sum(s.duration_seconds for s in sessions) == 60
