"""bookmarks: exact position (anchor triple) + client-id/tombstone sync

Revision ID: 0010_smart_bookmarks
Revises: 0009_reading_session_duration
Create Date: 2026-09-05

Design 2026-09-05-smart-bookmarks §3, §4, §6.

Two changes to one table:

**Precision.** ``page INTEGER`` becomes the generic anchor triple
``(anchor_index, anchor_fraction, anchor_total)`` plus a ``media_type``
discriminator saying whether ``anchor_index`` counts pages (manga) or
paragraphs (novel), and ``chapter_number`` so the bookmark survives a source
re-keying its chapters. See ``database.models.Bookmark`` for why one generic
set beats two medium-specific ones.

**Sync.** ``client_id`` (client-generated, unique per profile) plus a
``deleted_at`` tombstone and an ``updated_at`` clock, so a delete is not undone
by a stale device replaying its create outbox.

**Back-compat is the point of the backfill.** Every existing row survives with
its position intact: ``anchor_index = page`` (both 1-based, so this is a copy,
not a conversion), ``anchor_fraction = 0.0`` — an old page-only bookmark
resolves to the TOP of the page it named, which is exactly what it always
meant — ``anchor_total = 0`` ("the client never told us how many pages"), and
``media_type = 'manga'``, correct because the novel reader had no bookmark
affordance at all before this revision, so no novel bookmark can exist.
``updated_at`` seeds from ``created_at`` rather than from now(): a delta pull
must not report every pre-existing bookmark as freshly changed.

Done as an explicit table rebuild rather than ``batch_alter_table`` because the
change is a rename-with-generalization (``page`` -> ``anchor_index``), three
NOT NULL additions and a new UNIQUE constraint at once; spelling the target
shape out and moving the rows with one INSERT..SELECT is both auditable and
independent of the host SQLite's ALTER support.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_smart_bookmarks"
down_revision: Union[str, Sequence[str], None] = "0009_reading_session_duration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Rows per parameter batch when handing out client ids. The table is small in
#: practice; this only stops a pathological one from building one giant list.
_CHUNK = 500


def _new_table(name: str) -> None:
    """The post-revision ``bookmarks`` shape, mirroring ``models.Bookmark``."""
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("reading_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("series_key", sa.String(length=512), nullable=False),
        sa.Column("chapter_key", sa.String(length=512), nullable=False),
        sa.Column("chapter_number", sa.Float(), nullable=True),
        sa.Column(
            "media_type",
            sa.String(length=16),
            nullable=False,
            server_default="manga",
        ),
        sa.Column("anchor_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("anchor_fraction", sa.Float(), nullable=False, server_default="0"),
        sa.Column("anchor_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "profile_id", "client_id", name="uq_bookmarks_client_id"
        ),
    )


def _assign_client_ids(table: str) -> None:
    """Hand every migrated row a real uuid4.

    The INSERT..SELECT seeds a deterministic placeholder so the NOT NULL
    UNIQUE column is satisfiable in pure SQL; this replaces it with the same
    kind of id the clients generate, so nothing downstream has to special-case
    a migrated bookmark. Done in Python because SQLite has no uuid function.
    """
    bind = op.get_bind()
    ids = [row[0] for row in bind.execute(sa.text(f"SELECT id FROM {table}"))]
    statement = sa.text(f"UPDATE {table} SET client_id = :cid WHERE id = :rid")
    for start in range(0, len(ids), _CHUNK):
        bind.execute(
            statement,
            [{"cid": str(uuid.uuid4()), "rid": rid} for rid in ids[start : start + _CHUNK]],
        )


def upgrade() -> None:
    _new_table("bookmarks_new")
    op.execute(
        """
        INSERT INTO bookmarks_new (
            id, user_id, profile_id, client_id, source_id, series_key,
            chapter_key, chapter_number, media_type, anchor_index,
            anchor_fraction, anchor_total, note, deleted_at, created_at,
            updated_at
        )
        SELECT
            id,
            user_id,
            profile_id,
            'legacy-' || CAST(id AS TEXT),
            source_id,
            series_key,
            chapter_key,
            NULL,
            'manga',
            max(1, COALESCE(page, 1)),
            0.0,
            0,
            note,
            NULL,
            created_at,
            created_at
        FROM bookmarks
        """
    )
    _assign_client_ids("bookmarks_new")
    # Dropping the old table takes its three indexes with it, which is why the
    # new ones can reuse the same names below.
    op.drop_table("bookmarks")
    op.rename_table("bookmarks_new", "bookmarks")

    op.create_index("ix_bookmarks_user_id", "bookmarks", ["user_id"])
    op.create_index("ix_bookmarks_profile_id", "bookmarks", ["profile_id"])
    op.create_index(
        "ix_bookmarks_series",
        "bookmarks",
        ["user_id", "profile_id", "source_id", "series_key"],
    )
    op.create_index(
        "ix_bookmarks_updated_at",
        "bookmarks",
        ["user_id", "profile_id", "updated_at"],
    )


def downgrade() -> None:
    """Back to page-only bookmarks.

    Lossy by construction and deliberately so: the pre-revision table has
    nowhere to put a fraction, a paragraph index or a tombstone. Tombstoned
    rows are dropped rather than revived — a downgrade must not resurrect
    bookmarks the owner deleted, which is the exact failure the tombstone
    exists to prevent.
    """
    op.create_table(
        "bookmarks_old",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("reading_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("series_key", sa.String(length=512), nullable=False),
        sa.Column("chapter_key", sa.String(length=512), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.execute(
        """
        INSERT INTO bookmarks_old (
            id, user_id, profile_id, source_id, series_key, chapter_key,
            page, note, created_at
        )
        SELECT id, user_id, profile_id, source_id, series_key, chapter_key,
               max(1, anchor_index), note, created_at
        FROM bookmarks
        WHERE deleted_at IS NULL
        """
    )
    op.drop_table("bookmarks")
    op.rename_table("bookmarks_old", "bookmarks")
    op.create_index("ix_bookmarks_user_id", "bookmarks", ["user_id"])
    op.create_index("ix_bookmarks_profile_id", "bookmarks", ["profile_id"])
    op.create_index(
        "ix_bookmarks_series",
        "bookmarks",
        ["user_id", "profile_id", "source_id", "series_key"],
    )
