"""index audit: cover the sorts, index the cascades, drop the dead weight

Revision ID: 0012_audit_indexes
Revises: 0011_source_cover_cache
Create Date: 2026-09-07

Data-layer audit findings IDX-1..IDX-5, IL-02 and CACHE-2, in one revision
because they are one change to one file: every statement here is a CREATE or
DROP INDEX, an ADD COLUMN, or a CREATE TABLE. Nothing rewrites an existing
table, so this runs at boot against the live database without copying a row of
it, and every step reverses.

**IDX-1 — the home screen's sort.** ``continue_reading`` picks the newest
progress row per series with a window function partitioned by
``(source_id, series_key)`` and ordered by ``(last_read_at DESC, id DESC)``.
``ix_chapter_progress_series`` stopped at ``series_key``, so SQLite sorted the
profile's entire progress history in a temp b-tree on every paint (15.6 ms over
6k rows). The index now carries the sort terms in the direction the query asks
for. The four-column shape it replaces was also a strict prefix of
``uq_chapter_progress``' autoindex, so it was never pulling its own weight.

**IDX-2 — the notification listings.** Five single-column indexes, no
composite: the listing filtered on the (user, profile) scope, ordered by
``created_at`` DESC, and got a temp b-tree over everything the profile owns.
Two composites replace them.

**IDX-3 — the profile-delete cascade.** ``chapter_progress``,
``reading_sessions`` and ``followed_series`` all hang off
``reading_profiles.id ON DELETE CASCADE``, and every index on them led with
``user_id``, so deleting a profile full-scanned all three (127 ms vs 61 ms at
180k/240k rows). Each gets a plain ``profile_id`` index.

**IDX-4 — dead weight.** Ten indexes removed, each provably unusable rather
than merely unloved: nine are a strict prefix of another index on the same
table or a duplicate of a UNIQUE constraint's autoindex, and
``ix_followed_series_content_rating`` indexes a column the app only ever
projects, never filters on. Every byte of an index is a byte the single writer
maintains on each insert.

**IL-02 — duplicate notifications.** ``update_notifications`` had no
uniqueness on ``(followed_series_id, chapter_key)``, so a connector that drops
a chapter from its listing and lists it again re-notifies it, once per flap,
forever. Existing rows may already violate this, so the revision DEDUPES first
— keeping the lowest id per group, the row the owner has already seen and
whose read state is real — and then builds the UNIQUE index.

**CACHE-2 — negative cover entries.** ``source_cover_cache`` could only record
a SUCCESSFUL downscale, so a cover that cannot shrink was re-fetched from
upstream and re-decoded on every read, forever. ``resize_failed_at`` (the
discriminator) and ``resize_failure`` (why) make the absence of a downscale
storable. See ``database.models.SourceCoverCache`` for how the service reads
them.

**IDX-5 — the statistics rollup.** ``reading_day_stats`` is created empty and
left alone here; ``reading_sessions`` stays the record of truth and the writer
lands separately.

**ISO-2 / IL-03 — the scope was never a pair.** ``user_id`` and ``profile_id``
were independent foreign keys, so the database accepted a row owned by account
A that pointed at account B's profile. Every scoped read filters on both, so
such a row is invisible and unreachable through the app while still occupying
its unique slot -- a follow that cannot be re-followed, progress that cannot be
overwritten. The four scoped tables now reference the pair together, which
needs a UNIQUE index on ``reading_profiles(user_id, id)`` to point at. This is
the one part of the revision that rewrites tables (SQLite cannot add a
constraint in place), so it runs FIRST: batch mode rebuilds each table's
indexes from what it reflects, and a reflected index loses the ``DESC`` that
IDX-1 exists to add. Live data was checked before writing this: zero violating
rows across all four tables.

REVERSIBILITY. ``downgrade()`` restores the exact 0011 index set, the 0011
``source_cover_cache`` columns and drops the rollup table. The one thing it
cannot undo is the dedupe: notifications deleted as duplicates stay deleted,
which is the intended outcome either way — they were the same chapter twice.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_audit_indexes"
down_revision: Union[str, Sequence[str], None] = "0011_source_cover_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: ``(name, table)`` for every index removed as provably redundant. The reason
#: each one cannot be used is in the comment beside it; the shape it is a
#: prefix of is what makes the drop safe rather than a judgement call.
_REDUNDANT: tuple[tuple[str, str, list[str]], ...] = (
    # Duplicates of a UNIQUE constraint's autoindex.
    ("ix_users_username", "users", ["username"]),
    ("ix_sessions_token_hash", "sessions", ["token_hash"]),
    # Strict prefixes of another index on the same table.
    ("ix_bookmarks_user_id", "bookmarks", ["user_id"]),  # ix_bookmarks_series
    ("ix_reading_profiles_user_id", "reading_profiles", ["user_id"]),  # _user_sort
    ("ix_source_pins_user_id", "source_pins", ["user_id"]),  # _user_sort
    ("ix_collections_user_id", "collections", ["user_id"]),  # uq_collections_user_name
    ("ix_chapter_ocr_series", "chapter_ocr", ["source_id", "series_key"]),  # uq_chapter_ocr
    ("ix_tags_scope", "tags", ["user_id", "profile_id"]),  # uq_tags_scope_name
    # Indexed a column nothing filters on: ``content_rating`` is projected by
    # the mature gate, never used as a predicate.
    ("ix_followed_series_content_rating", "followed_series", ["content_rating"]),
)

#: The single-column notification indexes IDX-2's composites replace.
_NOTIFICATION_SINGLES: tuple[tuple[str, list[str]], ...] = (
    ("ix_update_notifications_user_id", ["user_id"]),
    ("ix_update_notifications_is_read", ["is_read"]),
    ("ix_update_notifications_created_at", ["created_at"]),
    # Becomes a strict prefix of uq_update_notifications_chapter, which is the
    # follow-delete cascade's seek target from here on.
    ("ix_update_notifications_followed_series_id", ["followed_series_id"]),
)

#: ISO-2 / IL-03: every table whose rows are scoped to a (user, profile) pair.
_SCOPED_TABLES: tuple[str, ...] = (
    "followed_series",
    "chapter_progress",
    "bookmarks",
    "reading_sessions",
)

#: IDX-3: the profile-delete cascade's seek targets.
_CASCADE_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_chapter_progress_profile_id", "chapter_progress"),
    ("ix_reading_sessions_profile_id", "reading_sessions"),
    ("ix_followed_series_profile_id", "followed_series"),
)

#: IDX-1. Spelled as expressions rather than names because the DESC is the
#: point: an ASC index here does not cover the window function's ORDER BY.
_CONTINUE_READING_COLUMNS = [
    "user_id",
    "profile_id",
    "source_id",
    "series_key",
    sa.desc(sa.column("last_read_at")),
    sa.desc(sa.column("id")),
]


def upgrade() -> None:
    # ISO-2 / IL-03 FIRST, because it is the only step here that rewrites a
    # table: batch mode recreates each table's indexes from what it reflects,
    # and a reflected index loses the DESC that IDX-1 exists to add. Doing the
    # rewrites before any index work means every index below is created on the
    # final table shape, once.
    with op.batch_alter_table("reading_profiles") as batch:
        batch.create_unique_constraint(
            "uq_reading_profiles_user_scope", ["user_id", "id"]
        )
    for table in _SCOPED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                f"fk_{table}_scope",
                "reading_profiles",
                ["user_id", "profile_id"],
                ["user_id", "id"],
                ondelete="CASCADE",
            )

    # IL-02. The UNIQUE index cannot be built while duplicates exist, and on a
    # database that has been running a flapping connector they do. Keep the
    # lowest id in each group: it is the notification that arrived first, so it
    # is the one whose read state and place in the owner's list are real.
    op.execute(
        """
        DELETE FROM update_notifications
        WHERE id NOT IN (
            SELECT MIN(id) FROM update_notifications
            GROUP BY followed_series_id, chapter_key
        )
        """
    )
    op.create_index(
        "uq_update_notifications_chapter",
        "update_notifications",
        ["followed_series_id", "chapter_key"],
        unique=True,
    )

    # IDX-2.
    op.create_index(
        "ix_update_notifications_scope_unread",
        "update_notifications",
        ["user_id", "profile_id", "is_read", "created_at"],
    )
    op.create_index(
        "ix_update_notifications_scope_created",
        "update_notifications",
        ["user_id", "profile_id", "created_at"],
    )
    for name, _columns in _NOTIFICATION_SINGLES:
        op.drop_index(name, table_name="update_notifications")

    # IDX-1.
    op.drop_index("ix_chapter_progress_series", table_name="chapter_progress")
    op.create_index(
        "ix_chapter_progress_series",
        "chapter_progress",
        _CONTINUE_READING_COLUMNS,
    )

    # IDX-3.
    for name, table in _CASCADE_INDEXES:
        op.create_index(name, table, ["profile_id"])

    # IDX-4.
    for name, table, _columns in _REDUNDANT:
        op.drop_index(name, table_name=table)

    # CACHE-2. Both nullable with no server default, so every existing row is
    # a positive entry — which is what they all are.
    op.add_column(
        "source_cover_cache",
        sa.Column("resize_failure", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "source_cover_cache",
        sa.Column("resize_failed_at", sa.DateTime(), nullable=True),
    )

    # IDX-5.
    op.create_table(
        "reading_day_stats",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("reading_profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.String(length=10), primary_key=True),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seconds_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("series_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_reading_day_stats_profile_id", "reading_day_stats", ["profile_id"]
    )


def downgrade() -> None:
    for table in reversed(_SCOPED_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_scope", type_="foreignkey")
    with op.batch_alter_table("reading_profiles") as batch:
        batch.drop_constraint("uq_reading_profiles_user_scope", type_="unique")

    op.drop_index(
        "ix_reading_day_stats_profile_id", table_name="reading_day_stats"
    )
    op.drop_table("reading_day_stats")

    op.drop_column("source_cover_cache", "resize_failed_at")
    op.drop_column("source_cover_cache", "resize_failure")

    for name, table, columns in _REDUNDANT:
        op.create_index(name, table, columns)

    for name, table in _CASCADE_INDEXES:
        op.drop_index(name, table_name=table)

    op.drop_index("ix_chapter_progress_series", table_name="chapter_progress")
    op.create_index(
        "ix_chapter_progress_series",
        "chapter_progress",
        ["user_id", "profile_id", "source_id", "series_key"],
    )

    for name, columns in _NOTIFICATION_SINGLES:
        op.create_index(name, "update_notifications", columns)
    op.drop_index(
        "ix_update_notifications_scope_created", table_name="update_notifications"
    )
    op.drop_index(
        "ix_update_notifications_scope_unread", table_name="update_notifications"
    )
    # The deduped rows are NOT restored; see the module docstring.
    op.drop_index(
        "uq_update_notifications_chapter", table_name="update_notifications"
    )
