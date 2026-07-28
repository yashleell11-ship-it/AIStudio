"""normalize pages.width/height to the two states the reader understands

Data-only. ``pages.width`` / ``pages.height`` have existed since the baseline,
so there is no schema change here and no ORM drift.

Context: nothing had ever written those columns. Every page in every existing
database has them null, so the reader laid its whole lazy list out on one
guessed aspect ratio and re-measured each page as its image arrived -- which is
the "scrolling randomly jumps me backwards" report. They are populated at scan
time now (``LibraryService._persist_scan``), and already-scanned chapters are
repaired by ``PageDimensionBackfill``.

**Why the backfill is not performed here.** Learning a page's size means opening
its file, and a real library holds hundreds of thousands of pages. Alembic runs
synchronously inside ``init_db()`` on every boot (``database.session.
run_alembic_migrations``), so a file-walking migration would stall startup for
minutes on a NAS, hold a write transaction the whole time, and -- because a
migration cannot be resumed halfway -- start over from nothing if the container
were restarted during it. The measurement is therefore driven off reads by a
single background daemon thread: opening a chapter enqueues that chapter and the
rest of its series, so the library repairs itself in reading order while the
owner reads, and no request ever waits on a file.

**What this revision does do** is fix the representation so those two mechanisms
and the client agree on what "unknown" looks like. The client treats a page as
measured only when both values are present *and positive*
(mobile/lib/features/reader/utils/page_layout.dart:55-62), while the filler
treats a page as done when neither is null. A row carrying a zero, a negative,
or only one of the pair would satisfy the filler and not the client: permanently
laid out on the default guess, and never re-measured because it no longer looks
unmeasured. Collapsing every such row back to null closes that gap and makes
``width IS NULL OR height IS NULL`` a complete predicate for "needs measuring".

On today's databases this matches zero rows -- no writer has ever produced a
partial pair. It is written anyway because it is the point at which the invariant
starts being relied upon, and because the columns are reachable by hand and by
restore from older backups. Idempotent and instant: a single indexed-free UPDATE
over a column set that is null everywhere.

Revision ID: a1f4c8b27d63
Revises: f3b71d0c9e42
Create Date: 2026-07-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f4c8b27d63"
down_revision: Union[str, Sequence[str], None] = "f3b71d0c9e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NORMALIZE = """
UPDATE pages
   SET width = NULL, height = NULL
 WHERE (width IS NULL) <> (height IS NULL)
    OR width <= 0
    OR height <= 0
"""


def upgrade() -> None:
    op.execute(sa.text(_NORMALIZE))


def downgrade() -> None:
    # Nothing to undo: this only ever replaces values that were already unusable
    # with the null that means the same thing, and the pre-revision code read
    # both as "no dimensions".
    pass
