"""backfill library membership for followed/downloaded series

Data-only. No schema change, so no ORM drift.

Why it is needed: object-level read authorization now requires the caller's
ACCOUNT to have a claim on a series (core.library_authz). Every claim-creating
path stamps the owner *going forward*, but two classes of already-downloaded
content never recorded one and would become unreadable by the person who asked
for it:

1. **Auto-downloads.** ``update_auto_download`` built its ``DownloadService``
   with no owner even though it held ``tracker.user_id`` / ``tracker.profile_id``
   (fixed in the same change). Every chapter that arrived because the owner
   *followed* a series therefore produced a ``Download`` of ``(NULL, NULL)``, and
   the worker filed the membership row in the unowned bucket.
2. **Downloads queued before ``downloads.user_id``/``profile_id`` existed** whose
   completion landed after the first admin registered — ``AuthService.
   _claim_unowned_data`` only re-owns rows that exist at registration time.

The join used here is the only one available. ``series_trackers.local_series_id``
looks like the natural link and is NOT usable: nothing in the codebase has ever
written it (see a7c3e51b90d4's note and core.content_rating), so it is NULL on
every row. The real bridge is the link table the download worker writes:

    series_trackers (source, series_id, user_id, profile_id)
      -> source_chapter_links (source, series_id) -> chapters.series_id

i.e. "this account follows a remote series, and chapters of that remote series
have been downloaded into this local series". That grants access only to series
the account demonstrably follows or has downloaded — never to the catalog at
large.

``in_library = 1`` rather than 0: this is the same state a *manual* download
produces (the worker's ``_persist_scan`` sets it), and it is what
``update_auto_download`` will now produce for every future auto-download. Filing
it as 0 would leave the followed series readable but permanently absent from the
grid, which is the bug 0dd7397 set out to fix — just for the auto-download half.

Idempotent: guarded by NOT EXISTS on the ``(user_id, profile_id, series_id)``
unique. Trackers with ``user_id IS NULL`` are skipped -- they name no account, and
their content stays reachable via the unowned-bucket arm of the predicate.

Revision ID: f3b71d0c9e42
Revises: e6d1c73f9a24
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b71d0c9e42"
down_revision: Union[str, Sequence[str], None] = "e6d1c73f9a24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BACKFILL = """
INSERT INTO user_series_state
    (user_id, profile_id, series_id, in_library, is_favorite, reading_status,
     read_chapters, created_at, updated_at)
SELECT DISTINCT
    t.user_id, t.profile_id, c.series_id, 1, 0, 'unread', 0,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM series_trackers AS t
JOIN source_chapter_links AS l
  ON l.source = t.source AND l.series_id = t.series_id
JOIN chapters AS c
  ON c.id = l.local_chapter_id
WHERE t.user_id IS NOT NULL
  AND NOT EXISTS (
        SELECT 1 FROM user_series_state AS s
        WHERE s.series_id = c.series_id
          AND s.user_id IS t.user_id
          AND s.profile_id IS t.profile_id
  )
"""


def upgrade() -> None:
    op.execute(sa.text(_BACKFILL))


def downgrade() -> None:
    # Not reversible: once written, these rows are indistinguishable from a row
    # the owner created by adding the series by hand, and deleting them would
    # throw away a real "add to library" action. Leaving them is harmless -- the
    # column predates this revision and every reader tolerates the row.
    pass
