"""multi-user ownership expand

Adds per-user ownership to every user-state table (household model): a nullable
``user_id`` foreign key, a new ``user_series_state`` table for per-user
favourite / reading-status / read-count (superseding the legacy columns on the
shared ``series`` row), and composite unique constraints so two users can hold
independent state for the same series/chapter/collection.

Expand-only: the legacy ``series.is_favorite`` / ``reading_status`` /
``read_chapters`` columns are left in place (a later contract migration drops
them) so the change is backward-compatible with un-migrated service code.

``user_id`` is nullable and existing rows are left unowned (NULL); the first
admin registration claims all NULL-owned rows (AuthService.register), so the
household owner keeps their pre-multi-user library state — no data loss.

Revision ID: efe6a4dc459e
Revises: c2b7350c254a
Create Date: 2026-07-11 15:22:39.547851
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "efe6a4dc459e"
down_revision: Union[str, Sequence[str], None] = "c2b7350c254a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Names the reflected (previously inline/unnamed) unique constraints so batch
# mode can drop them on SQLite — otherwise the old single-column unique survives
# the table rebuild and blocks two users sharing a series/chapter/collection.
_NAMING = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
}


def _add_owner(batch_op) -> None:
    batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))


def upgrade() -> None:
    # --- new per-user state table -------------------------------------------
    op.create_table(
        "user_series_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("is_favorite", sa.Integer(), nullable=False),
        sa.Column("reading_status", sa.String(length=64), nullable=False),
        sa.Column("read_chapters", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "series_id", name="uq_user_series_state"),
    )
    with op.batch_alter_table("user_series_state", schema=None) as batch_op:
        batch_op.create_index("ix_user_series_state_series", ["series_id"], unique=False)
        batch_op.create_index("ix_user_series_state_user", ["user_id"], unique=False)
        batch_op.create_index(
            "ix_user_series_state_user_favorite", ["user_id", "is_favorite"], unique=False
        )
        batch_op.create_index(
            "ix_user_series_state_user_status", ["user_id", "reading_status"], unique=False
        )

    # Backfill per-user state from the legacy shared columns, unowned (user_id
    # NULL) until the first admin claims it. Only rows with non-default state are
    # materialised — absence means the defaults (not favourite, unread, 0 read).
    op.execute(
        """
        INSERT INTO user_series_state
            (user_id, series_id, is_favorite, reading_status, read_chapters,
             created_at, updated_at)
        SELECT NULL, id, is_favorite, reading_status, read_chapters,
               created_at, updated_at
        FROM series
        WHERE is_favorite = 1 OR reading_status != 'unread' OR read_chapters > 0
        """
    )

    # --- add owner to the simple per-user tables ----------------------------
    for table in ("bookmarks", "downloads", "reading_sessions", "update_notifications"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            _add_owner(batch_op)
            batch_op.create_index(f"ix_{table}_user_id", ["user_id"], unique=False)
            batch_op.create_foreign_key(f"fk_{table}_user_id", "users", ["user_id"], ["id"])

    # --- tables whose OLD single-column unique must become composite ---------
    # reading_progress: series_id -> (user_id, series_id)
    with op.batch_alter_table(
        "reading_progress", schema=None, naming_convention=_NAMING
    ) as batch_op:
        _add_owner(batch_op)
        batch_op.drop_constraint("uq_reading_progress_series_id", type_="unique")
        batch_op.create_index("ix_reading_progress_user_id", ["user_id"], unique=False)
        batch_op.create_unique_constraint(
            "uq_reading_progress_user_series", ["user_id", "series_id"]
        )
        batch_op.create_foreign_key(
            "fk_reading_progress_user_id", "users", ["user_id"], ["id"]
        )

    # chapter_progress: chapter_id -> (user_id, chapter_id)
    with op.batch_alter_table(
        "chapter_progress", schema=None, naming_convention=_NAMING
    ) as batch_op:
        _add_owner(batch_op)
        batch_op.drop_constraint("uq_chapter_progress_chapter_id", type_="unique")
        batch_op.create_index("ix_chapter_progress_user_id", ["user_id"], unique=False)
        batch_op.create_unique_constraint(
            "uq_chapter_progress_user_chapter", ["user_id", "chapter_id"]
        )
        batch_op.create_foreign_key(
            "fk_chapter_progress_user_id", "users", ["user_id"], ["id"]
        )

    # collections: name -> (user_id, name)
    with op.batch_alter_table(
        "collections", schema=None, naming_convention=_NAMING
    ) as batch_op:
        _add_owner(batch_op)
        batch_op.drop_constraint("uq_collections_name", type_="unique")
        batch_op.create_index("ix_collections_user_id", ["user_id"], unique=False)
        batch_op.create_unique_constraint("uq_collections_user_name", ["user_id", "name"])
        batch_op.create_foreign_key("fk_collections_user_id", "users", ["user_id"], ["id"])

    # series_trackers: (source, series_id, track_kind) -> + user_id
    with op.batch_alter_table("series_trackers", schema=None) as batch_op:
        _add_owner(batch_op)
        batch_op.drop_constraint("uq_series_tracker", type_="unique")
        batch_op.create_unique_constraint(
            "uq_series_tracker", ["user_id", "source", "series_id", "track_kind"]
        )
        batch_op.create_index("ix_series_trackers_user_id", ["user_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_series_trackers_user_id", "users", ["user_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("series_trackers", schema=None) as batch_op:
        batch_op.drop_constraint("fk_series_trackers_user_id", type_="foreignkey")
        batch_op.drop_index("ix_series_trackers_user_id")
        batch_op.drop_constraint("uq_series_tracker", type_="unique")
        batch_op.create_unique_constraint(
            "uq_series_tracker", ["source", "series_id", "track_kind"]
        )
        batch_op.drop_column("user_id")

    with op.batch_alter_table("collections", schema=None) as batch_op:
        batch_op.drop_constraint("fk_collections_user_id", type_="foreignkey")
        batch_op.drop_constraint("uq_collections_user_name", type_="unique")
        batch_op.drop_index("ix_collections_user_id")
        batch_op.create_unique_constraint("uq_collections_name", ["name"])
        batch_op.drop_column("user_id")

    with op.batch_alter_table("chapter_progress", schema=None) as batch_op:
        batch_op.drop_constraint("fk_chapter_progress_user_id", type_="foreignkey")
        batch_op.drop_constraint("uq_chapter_progress_user_chapter", type_="unique")
        batch_op.drop_index("ix_chapter_progress_user_id")
        batch_op.create_unique_constraint("uq_chapter_progress_chapter_id", ["chapter_id"])
        batch_op.drop_column("user_id")

    with op.batch_alter_table("reading_progress", schema=None) as batch_op:
        batch_op.drop_constraint("fk_reading_progress_user_id", type_="foreignkey")
        batch_op.drop_constraint("uq_reading_progress_user_series", type_="unique")
        batch_op.drop_index("ix_reading_progress_user_id")
        batch_op.create_unique_constraint("uq_reading_progress_series_id", ["series_id"])
        batch_op.drop_column("user_id")

    for table in ("update_notifications", "reading_sessions", "downloads", "bookmarks"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_user_id", type_="foreignkey")
            batch_op.drop_index(f"ix_{table}_user_id")
            batch_op.drop_column("user_id")

    op.drop_table("user_series_state")
