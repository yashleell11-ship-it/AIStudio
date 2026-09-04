"""reading_session_stats_index: index the per-series roll-up key

Revision ID: 0006_reading_session_stats_index
Revises: 0005_single_admin_guard
Create Date: 2026-09-04

``reading_sessions`` was write-only until the statistics screen started
reading it, so its single index covered the write path's shape
``(user_id, profile_id, started_at)`` and nothing else. The per-source and
per-series breakdowns group by ``(user_id, profile_id, source_id,
series_key)``, and that is also the join key onto ``followed_series`` that
resolves the 18+ gate — on the old index both meant scanning and sorting the
profile's entire session history on every statistics request.

Mirrors ``ix_chapter_progress_series``, which exists for the same reason on
the sibling table.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006_reading_session_stats_index"
down_revision: Union[str, Sequence[str], None] = "0005_single_admin_guard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_reading_sessions_series",
        "reading_sessions",
        ["user_id", "profile_id", "source_id", "series_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_reading_sessions_series", table_name="reading_sessions")
