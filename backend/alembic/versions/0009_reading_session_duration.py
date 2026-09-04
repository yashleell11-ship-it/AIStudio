"""reading_sessions.duration_seconds: denormalized ended_at - started_at

Revision ID: 0009_reading_session_duration
Revises: 0008_followed_series_chapter_count
Create Date: 2026-09-04

Every roll-up on the statistics screen sums reading time, and the sum was
computed from the two timestamps in SQL: ``strftime('%s', ended_at) -
strftime('%s', started_at)``, i.e. two text-to-time parses per row, per
roll-up, six roll-ups per request. Measured over 12,008 sessions on the VPS
that was 15 ms of the 32 ms a totals query took, and 2.15x on the hour
histogram.

The column stores the raw elapsed seconds, floored at 0 (an unclosed session
and a clock-skewed one both count as 0, exactly as the old expression did).
``SESSION_SECONDS_CAP`` is deliberately *not* baked in: the cap is a reading
policy, so it stays applied at read time and can be retuned without touching
stored data.

Maintained by a ``before_insert`` / ``before_update`` mapper listener on
``ReadingSession`` (``database/models.py``) rather than by its writer, because
the value derives from two columns and the mapper hook sees the finished row.
``reading_sessions`` is append-only, so in practice only the insert path fires.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_reading_session_duration"
down_revision: Union[str, Sequence[str], None] = "0008_followed_series_chapter_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reading_sessions",
        sa.Column(
            "duration_seconds", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    # Backfill with the very expression the read path used to evaluate, so
    # existing history keeps reporting exactly the same numbers. This one is
    # safe to do in SQL: ``strftime`` is core SQLite, not the JSON extension.
    op.execute(
        """
        UPDATE reading_sessions
           SET duration_seconds = CASE
                 WHEN ended_at IS NULL THEN 0
                 ELSE max(0,
                          CAST(strftime('%s', ended_at) AS INTEGER)
                        - CAST(strftime('%s', started_at) AS INTEGER))
               END
        """
    )


def downgrade() -> None:
    op.drop_column("reading_sessions", "duration_seconds")
