"""source_cover_cache: pre-rendered downscaled covers for ``?w=``

Revision ID: 0011_source_cover_cache
Revises: 0010_smart_bookmarks
Create Date: 2026-09-05

Measured in a browser at a 375 px viewport, 13 of the 24 covers on one
``/sources/mangadex`` page transferred 20.79 MB (mean 1.64 MB, max 6.27 MB)
into a 153x230 CSS px box — a 40-60x overdraw on every browse, library and
search screen. ``next/image`` cannot fix it (its optimizer sends no cookies
and the cover route requires ``mm_session``), so the cover proxy grew a
``?w=`` parameter that renders the size the client will actually paint.

This table is what stops a 2-vCPU box re-rendering the same cover twice.
Rows are the encoded WebP/JPEG bytes, keyed by everything they depend on:
``(source_id, series_key, width, fmt)``. Widths snap onto the closed
``image_resize.COVER_WIDTHS`` set, so the key space is bounded per series.

Rows are GLOBAL. The per-caller 18+ gate is applied on every read before
this table is touched (``SourceCacheService.get_series_cover`` ->
``BrowseService.ensure_visible``), exactly as for ``source_browse_cache``:
the gate is about the reader, the bytes are about the series.

Bounded by TOTAL BYTES with LRU eviction (``last_used_at`` — hence the
index), not by row count: these rows are binary and uneven, so a row cap
would be a bad proxy for the disk they occupy. ``byte_size`` sits before
``data`` in the column order so the sweep's SUM does not have to walk blob
overflow pages.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_source_cover_cache"
down_revision: Union[str, Sequence[str], None] = "0010_smart_bookmarks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_cover_cache",
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("series_key", sa.String(length=512), primary_key=True),
        sa.Column("width", sa.Integer(), primary_key=True),
        sa.Column("fmt", sa.String(length=8), primary_key=True),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_source_cover_cache_last_used_at",
        "source_cover_cache",
        ["last_used_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_cover_cache_last_used_at", table_name="source_cover_cache"
    )
    op.drop_table("source_cover_cache")
