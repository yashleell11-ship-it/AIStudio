"""profile scoped data

Adds per-profile ownership (Netflix-style profiles) to every user-state table:
a nullable ``profile_id`` foreign key (ON DELETE CASCADE → reading_profiles),
and reworks the composite unique constraints to include ``profile_id`` so two
profiles on the SAME account can hold independent state for the same
series/chapter/collection/tracker. Also adds a per-profile
``mature_content_enabled`` gate to ``reading_profiles``.

``profile_id`` is kept NULLABLE: legacy rows with ``user_id IS NULL`` cannot be
attributed to a profile, and NULL-profile rows are the "unscoped"/legacy bucket.
Uniqueness with a NULL profile_id is not DB-enforced (SQLite treats NULLs as
distinct); enforcement of "one active profile per mutation" lives in the app
layer (core.profile_context).

Backfill: for every scoped row with a non-null ``user_id`` we set
``profile_id`` to that user's OLDEST profile (min sort_order, then min id). If a
user owns scoped rows but has NO profile yet, a 'Default' profile is created for
them first. Rows with ``user_id IS NULL`` keep ``profile_id NULL``.

Revision ID: d4e8f1a2b3c9
Revises: c29b60ed8738
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e8f1a2b3c9"
down_revision: Union[str, Sequence[str], None] = "c29b60ed8738"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that gain a plain profile_id (no unique rework).
_SIMPLE_TABLES = ("bookmarks", "reading_sessions", "update_notifications")

# Every table that owns scoped rows keyed by user_id (used for the backfill).
_SCOPED_TABLES = (
    "reading_progress",
    "chapter_progress",
    "reading_sessions",
    "bookmarks",
    "collections",
    "user_series_state",
    "series_trackers",
    "update_notifications",
)


def _add_profile_col(batch_op) -> None:
    batch_op.add_column(sa.Column("profile_id", sa.Integer(), nullable=True))


def _add_fk_and_index(batch_op, table: str) -> None:
    batch_op.create_index(f"ix_{table}_profile_id", ["profile_id"], unique=False)
    batch_op.create_foreign_key(
        f"fk_{table}_profile_id",
        "reading_profiles",
        ["profile_id"],
        ["id"],
        ondelete="CASCADE",
    )


def upgrade() -> None:
    # --- per-profile mature gate on the profile itself ----------------------
    with op.batch_alter_table("reading_profiles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mature_content_enabled",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    # --- simple tables: add profile_id + index + fk -------------------------
    for table in _SIMPLE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            _add_profile_col(batch_op)
            _add_fk_and_index(batch_op, table)

    # --- tables whose composite unique must gain profile_id -----------------
    with op.batch_alter_table("reading_progress", schema=None) as batch_op:
        _add_profile_col(batch_op)
        batch_op.drop_constraint("uq_reading_progress_user_series", type_="unique")
        batch_op.create_unique_constraint(
            "uq_reading_progress_user_series",
            ["user_id", "profile_id", "series_id"],
        )
        _add_fk_and_index(batch_op, "reading_progress")

    with op.batch_alter_table("chapter_progress", schema=None) as batch_op:
        _add_profile_col(batch_op)
        batch_op.drop_constraint("uq_chapter_progress_user_chapter", type_="unique")
        batch_op.create_unique_constraint(
            "uq_chapter_progress_user_chapter",
            ["user_id", "profile_id", "chapter_id"],
        )
        _add_fk_and_index(batch_op, "chapter_progress")

    with op.batch_alter_table("collections", schema=None) as batch_op:
        _add_profile_col(batch_op)
        batch_op.drop_constraint("uq_collections_user_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_collections_user_name", ["user_id", "profile_id", "name"]
        )
        _add_fk_and_index(batch_op, "collections")

    with op.batch_alter_table("user_series_state", schema=None) as batch_op:
        _add_profile_col(batch_op)
        batch_op.drop_constraint("uq_user_series_state", type_="unique")
        batch_op.create_unique_constraint(
            "uq_user_series_state", ["user_id", "profile_id", "series_id"]
        )
        _add_fk_and_index(batch_op, "user_series_state")

    with op.batch_alter_table("series_trackers", schema=None) as batch_op:
        _add_profile_col(batch_op)
        batch_op.drop_constraint("uq_series_tracker", type_="unique")
        batch_op.create_unique_constraint(
            "uq_series_tracker",
            ["user_id", "profile_id", "source", "series_id", "track_kind"],
        )
        _add_fk_and_index(batch_op, "series_trackers")

    # --- backfill -----------------------------------------------------------
    # 1) Every user who owns scoped rows but has no profile gets a 'Default'.
    owners_union = " UNION ".join(
        f"SELECT user_id FROM {table} WHERE user_id IS NOT NULL"
        for table in _SCOPED_TABLES
    )
    op.execute(
        f"""
        INSERT INTO reading_profiles
            (user_id, name, avatar_key, mood, sort_order,
             mature_content_enabled, created_at)
        SELECT DISTINCT u.user_id, 'Default', 'default', 'default', 0, 0,
               CURRENT_TIMESTAMP
        FROM ({owners_union}) AS u
        WHERE NOT EXISTS (
            SELECT 1 FROM reading_profiles p WHERE p.user_id = u.user_id
        )
        """
    )

    # 2) Attribute each scoped row to its owner's oldest profile.
    for table in _SCOPED_TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET profile_id = (
                SELECT p.id FROM reading_profiles p
                WHERE p.user_id = {table}.user_id
                ORDER BY p.sort_order ASC, p.id ASC
                LIMIT 1
            )
            WHERE user_id IS NOT NULL
            """
        )


def downgrade() -> None:
    with op.batch_alter_table("series_trackers", schema=None) as batch_op:
        batch_op.drop_constraint("fk_series_trackers_profile_id", type_="foreignkey")
        batch_op.drop_index("ix_series_trackers_profile_id")
        batch_op.drop_constraint("uq_series_tracker", type_="unique")
        batch_op.create_unique_constraint(
            "uq_series_tracker", ["user_id", "source", "series_id", "track_kind"]
        )
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("user_series_state", schema=None) as batch_op:
        batch_op.drop_constraint("fk_user_series_state_profile_id", type_="foreignkey")
        batch_op.drop_index("ix_user_series_state_profile_id")
        batch_op.drop_constraint("uq_user_series_state", type_="unique")
        batch_op.create_unique_constraint(
            "uq_user_series_state", ["user_id", "series_id"]
        )
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("collections", schema=None) as batch_op:
        batch_op.drop_constraint("fk_collections_profile_id", type_="foreignkey")
        batch_op.drop_index("ix_collections_profile_id")
        batch_op.drop_constraint("uq_collections_user_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_collections_user_name", ["user_id", "name"]
        )
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("chapter_progress", schema=None) as batch_op:
        batch_op.drop_constraint("fk_chapter_progress_profile_id", type_="foreignkey")
        batch_op.drop_index("ix_chapter_progress_profile_id")
        batch_op.drop_constraint("uq_chapter_progress_user_chapter", type_="unique")
        batch_op.create_unique_constraint(
            "uq_chapter_progress_user_chapter", ["user_id", "chapter_id"]
        )
        batch_op.drop_column("profile_id")

    with op.batch_alter_table("reading_progress", schema=None) as batch_op:
        batch_op.drop_constraint("fk_reading_progress_profile_id", type_="foreignkey")
        batch_op.drop_index("ix_reading_progress_profile_id")
        batch_op.drop_constraint("uq_reading_progress_user_series", type_="unique")
        batch_op.create_unique_constraint(
            "uq_reading_progress_user_series", ["user_id", "series_id"]
        )
        batch_op.drop_column("profile_id")

    for table in _SIMPLE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_profile_id", type_="foreignkey")
            batch_op.drop_index(f"ix_{table}_profile_id")
            batch_op.drop_column("profile_id")

    with op.batch_alter_table("reading_profiles", schema=None) as batch_op:
        batch_op.drop_column("mature_content_enabled")
