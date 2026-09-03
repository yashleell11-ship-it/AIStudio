"""tags become per-(user_id, profile_id)

Revision ID: 0002_tags_per_profile
Revises: 0001_source_native
Create Date: 2026-09-03

``tags`` was the one profile-owned surface still stored globally: a single row
set with a UNIQUE(name), shared by every account. That leaked two ways —
``DELETE /library/tags/{id}`` removed a row everybody read (and, through the
``profile_series_tags`` ON DELETE CASCADE, every account's associations with
it), and creating a tag whose name already existed anywhere handed the caller
somebody else's row. Tag names are user-authored text, so the vocabulary is
owned data and the boundary is ``(user_id, profile_id)`` like everything else.

SQLite cannot drop a UNIQUE constraint in place, so ``tags`` is rebuilt.

**Data migration.** Ownership is recovered from ``profile_series_tags``: every
distinct ``(user_id, profile_id)`` that used a tag gets its own copy of it, and
its associations are repointed at that copy. A tag two profiles both used
therefore becomes two independent tags — which is what it should always have
been. A tag with **no** associations carries no recoverable owner and is
dropped; that is the only data this revision destroys, and it is limited to
vocabulary entries that were created and never applied to a series.

Foreign keys are not enforced during migration (``alembic/env.py`` builds its
own engine, without the ``PRAGMA foreign_keys=ON`` that
``database.session.get_engine`` installs), so the rebuild can repoint
``profile_series_tags.tag_id`` before the new parent table takes the name.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tags_per_profile"
down_revision: Union[str, Sequence[str], None] = "0001_source_native"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _new_tags_table(name: str) -> None:
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
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "profile_id", "name", name="uq_tags_scope_name"
        ),
    )


def upgrade() -> None:
    # Scratch mapping table: which legacy tag became which owned tag. Plain
    # columns, no constraints — it is dropped at the end.
    op.create_table(
        "tags_id_map",
        sa.Column("new_id", sa.Integer(), primary_key=True),
        sa.Column("legacy_tag_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # One owned copy per (user, profile) that actually used the tag. ``name``
    # was globally unique, so a legacy tag maps to exactly one row per scope.
    op.execute(
        """
        INSERT INTO tags_id_map
            (legacy_tag_id, user_id, profile_id, name, category, color, created_at)
        SELECT DISTINCT
            t.id, pst.user_id, pst.profile_id, t.name, t.category, t.color,
            t.created_at
        FROM tags t
        JOIN profile_series_tags pst ON pst.tag_id = t.id
        """
    )

    _new_tags_table("tags_new")
    op.execute(
        """
        INSERT INTO tags_new
            (id, user_id, profile_id, name, category, color, created_at)
        SELECT new_id, user_id, profile_id, name, category, color, created_at
        FROM tags_id_map
        """
    )

    # Single pass, reading the map (not ``tags_new``), so a new id that happens
    # to equal some other row's legacy id cannot be remapped twice.
    op.execute(
        """
        UPDATE profile_series_tags
        SET tag_id = (
            SELECT m.new_id FROM tags_id_map m
            WHERE m.legacy_tag_id = profile_series_tags.tag_id
              AND m.user_id = profile_series_tags.user_id
              AND m.profile_id = profile_series_tags.profile_id
        )
        WHERE EXISTS (
            SELECT 1 FROM tags_id_map m
            WHERE m.legacy_tag_id = profile_series_tags.tag_id
              AND m.user_id = profile_series_tags.user_id
              AND m.profile_id = profile_series_tags.profile_id
        )
        """
    )

    op.drop_table("tags")
    op.rename_table("tags_new", "tags")
    op.drop_table("tags_id_map")
    op.create_index("ix_tags_scope", "tags", ["user_id", "profile_id"])


def downgrade() -> None:
    """Collapse back to one global vocabulary.

    Lossy in the other direction: two profiles' identically-named tags merge
    into one row, and the associations of all but the surviving row are
    repointed at it.
    """
    op.drop_index("ix_tags_scope", table_name="tags")
    op.create_table(
        "tags_old",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.execute(
        """
        INSERT INTO tags_old (name, category, color, created_at)
        SELECT name, MIN(category), MIN(color), MIN(created_at)
        FROM tags GROUP BY name
        """
    )
    op.execute(
        """
        UPDATE profile_series_tags
        SET tag_id = (
            SELECT o.id FROM tags_old o
            JOIN tags t ON t.name = o.name
            WHERE t.id = profile_series_tags.tag_id
        )
        WHERE EXISTS (
            SELECT 1 FROM tags_old o
            JOIN tags t ON t.name = o.name
            WHERE t.id = profile_series_tags.tag_id
        )
        """
    )
    op.drop_table("tags")
    op.rename_table("tags_old", "tags")
