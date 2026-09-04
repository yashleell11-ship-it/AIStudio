"""novel_chapter_cache: sanitized plain-text chapter cache for novel sources

Revision ID: 0007_novel_chapter_cache
Revises: 0006_reading_session_stats_index
Create Date: 2026-09-04

Novels land as sources (spec 2026-09-04-novels-design §3): identity is the
same ``(source_id, series_key, chapter_key)`` triple, but the payload is
TEXT, not page images, so — uniquely — it may be cached server-side without
violating the no-chapter-bytes rule (that rule exists for multi-GB image
libraries; a chapter is ~15 KB of paragraphs). Rows store the SANITIZED
plain-text paragraph array (JSON), which is both the wire shape of
``GET /novels/chapter`` and the input a future TTS pipeline reads.

Long TTL + stale-on-failure like the browse cache; bounded by
``Settings.novel_cache_max_rows`` with least-recently-USED eviction
(``last_used_at`` is bumped on every cache hit — hence the index). The
table exists regardless of MM_NOVELS_ENABLED; it simply stays empty while
the flag is off.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_novel_chapter_cache"
down_revision: Union[str, Sequence[str], None] = "0006_reading_session_stats_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "novel_chapter_cache",
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("series_key", sa.String(length=512), primary_key=True),
        sa.Column("chapter_key", sa.String(length=512), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("chapter_number", sa.Float(), nullable=True),
        sa.Column("paragraphs", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("prev_key", sa.String(length=512), nullable=True),
        sa.Column("next_key", sa.String(length=512), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_novel_chapter_cache_last_used_at",
        "novel_chapter_cache",
        ["last_used_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_novel_chapter_cache_last_used_at", table_name="novel_chapter_cache"
    )
    op.drop_table("novel_chapter_cache")
