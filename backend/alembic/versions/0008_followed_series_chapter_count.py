"""followed_series.chapter_count: denormalized len(known_chapters)

Revision ID: 0008_followed_series_chapter_count
Revises: 0007_novel_chapter_cache
Create Date: 2026-09-04

``known_chapters`` holds a followed series' entire chapter list as JSON —
kilobytes per row, and 17 KB is ordinary for a long-running series. The library
list endpoints print a chapter *count* per row and read nothing else off that
array, so producing one page of 40 series meant SQLite reading ~700 KB of text
off disk, SQLAlchemy building 40 Python strings and ``json.loads`` running 40
times, all to print 40 integers. Measured on a seeded 302-follow copy of the
production database, one page of ``GET /library/series`` was 832 KB and 105 ms.

This column carries the count so those paths never load the blob at all. It is
maintained by an attribute listener on ``FollowedSeries.known_chapters``
(``database/models.py``), which fires on every assignment including the
declarative constructor's keyword — there is no way to write the array without
the count following it, so the two cannot drift.

The backfill parses the JSON in Python rather than in SQL. ``json_array_length``
would be one statement, but the JSON1 functions are only compiled in by default
from SQLite 3.38 and this migration runs during application boot
(``database.session.init_db``), where a hard failure takes the whole service
down. Python's ``json`` is always there, the row count is bounded by
``max_follows_per_profile`` per profile, and parsing gives the exact same answer
the readers get.
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_followed_series_chapter_count"
down_revision: Union[str, Sequence[str], None] = "0007_novel_chapter_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _count(blob: object) -> int:
    """``len(known_chapters)``, mirroring the readers' ``_loads(...) or []``.

    Anything that is not a JSON array counts as 0 rather than failing the
    migration: a corrupt row should degrade to "no chapters", exactly as it
    already does on the read side.
    """
    if not blob:
        return 0
    try:
        parsed = json.loads(blob)
    except (TypeError, ValueError):
        return 0
    return len(parsed) if isinstance(parsed, list) else 0


def upgrade() -> None:
    op.add_column(
        "followed_series",
        sa.Column("chapter_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill. A fresh database has no rows and this is a no-op; an existing
    # one gets exact counts with no refetch from any source.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, known_chapters FROM followed_series "
            "WHERE known_chapters IS NOT NULL AND known_chapters NOT IN ('', '[]')"
        )
    ).all()
    update = sa.text("UPDATE followed_series SET chapter_count = :n WHERE id = :id")
    for row_id, blob in rows:
        count = _count(blob)
        if count:
            bind.execute(update, {"n": count, "id": row_id})


def downgrade() -> None:
    op.drop_column("followed_series", "chapter_count")
