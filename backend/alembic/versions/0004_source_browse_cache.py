"""source_browse_cache: cache one browse page per (source, sort, genre, page)

Revision ID: 0004_source_browse_cache
Revises: 0003_bootstrap_state
Create Date: 2026-09-04

Opening a source took 5-15s because every browse re-scraped the connector
live — ``source_series_cache`` (spec §3.10) only ever cached *per-series*
metadata, never the listing grid itself. This table caches one browse page,
keyed by everything that varies the result. Rows are small serialized JSON
listings, global like ``source_series_cache`` (the 18+ gate is applied per
caller on read), disposable at any time, and bounded by
``Settings.browse_cache_max_rows`` via oldest-``fetched_at`` eviction — hence
the index.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_source_browse_cache"
down_revision: Union[str, Sequence[str], None] = "0003_bootstrap_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_browse_cache",
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("sort", sa.String(length=64), primary_key=True),
        sa.Column("genre", sa.String(length=128), primary_key=True),
        sa.Column("page", sa.Integer(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_source_browse_cache_fetched_at", "source_browse_cache", ["fetched_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_browse_cache_fetched_at", table_name="source_browse_cache")
    op.drop_table("source_browse_cache")
