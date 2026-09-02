"""source-native baseline

Revision ID: 0001_source_native
Revises:
Create Date: 2026-09-03

The database is wiped for the VPS slim-down. This is the sole baseline: it
creates the full source-native schema (accounts/profiles + followed_series +
progress/history + collections/tags + notifications + chapter_ocr + the
source_series_cache), plus the ``chapter_ocr_fts`` FTS5 virtual table and its
AI/AD/AU sync triggers over ``chapter_ocr.full_text``.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_source_native"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "reading_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("avatar_key", sa.String(length=64), nullable=False),
        sa.Column("mood", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "mature_content_enabled",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reading_profiles_user_id", "reading_profiles", ["user_id"])
    op.create_index(
        "ix_reading_profiles_user_sort", "reading_profiles", ["user_id", "sort_order"]
    )

    op.create_table(
        "source_pins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("reading_profiles.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "profile_id", "source_id", name="uq_source_pins_user_source"
        ),
    )
    op.create_index("ix_source_pins_user_id", "source_pins", ["user_id"])
    op.create_index("ix_source_pins_profile_id", "source_pins", ["profile_id"])
    op.create_index(
        "ix_source_pins_user_sort",
        "source_pins",
        ["user_id", "profile_id", "sort_order"],
    )

    op.create_table(
        "source_health",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_id", name="uq_source_health_source_id"),
    )
    op.create_index(
        "ix_source_health_consecutive_failures",
        "source_health",
        ["consecutive_failures"],
    )

    op.create_table(
        "update_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("notify_enabled", sa.Integer(), nullable=False),
        sa.Column("check_on_startup", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "update_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("series_checked", sa.Integer(), nullable=False),
        sa.Column("new_chapters_found", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_update_runs_started_at", "update_runs", ["started_at"])

    op.create_table(
        "followed_series",
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
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("cover_url", sa.String(length=1024), nullable=True),
        sa.Column("is_favorite", sa.Integer(), nullable=False),
        sa.Column("reading_status", sa.String(length=32), nullable=False),
        sa.Column("notify", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("content_rating", sa.String(length=32), nullable=True),
        sa.Column("mature_override", sa.Integer(), nullable=True),
        sa.Column(
            "known_chapters", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("migrated_from_source", sa.String(length=64), nullable=True),
        sa.Column("migrated_from_series_key", sa.String(length=512), nullable=True),
        sa.Column("migrated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "profile_id",
            "source_id",
            "series_key",
            name="uq_followed_series",
        ),
    )
    op.create_index(
        "ix_followed_series_library",
        "followed_series",
        ["user_id", "profile_id", "sort_order"],
    )
    op.create_index("ix_followed_series_source_id", "followed_series", ["source_id"])
    op.create_index(
        "ix_followed_series_favorite",
        "followed_series",
        ["user_id", "profile_id", "is_favorite"],
    )
    op.create_index(
        "ix_followed_series_content_rating", "followed_series", ["content_rating"]
    )

    op.create_table(
        "chapter_progress",
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
        sa.Column("chapter_number", sa.Float(), nullable=True),
        sa.Column("last_page", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("scroll_offset_px", sa.Integer(), nullable=False),
        sa.Column("is_completed", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "profile_id",
            "source_id",
            "series_key",
            "chapter_key",
            name="uq_chapter_progress",
        ),
    )
    op.create_index(
        "ix_chapter_progress_last_read",
        "chapter_progress",
        ["user_id", "profile_id", "last_read_at"],
    )
    op.create_index(
        "ix_chapter_progress_series",
        "chapter_progress",
        ["user_id", "profile_id", "source_id", "series_key"],
    )

    op.create_table(
        "bookmarks",
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
    op.create_index("ix_bookmarks_user_id", "bookmarks", ["user_id"])
    op.create_index("ix_bookmarks_profile_id", "bookmarks", ["profile_id"])
    op.create_index(
        "ix_bookmarks_series",
        "bookmarks",
        ["user_id", "profile_id", "source_id", "series_key"],
    )

    op.create_table(
        "reading_sessions",
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
        sa.Column("chapter_number", sa.Float(), nullable=True),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("pages_read", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_reading_sessions_started_at",
        "reading_sessions",
        ["user_id", "profile_id", "started_at"],
    )

    op.create_table(
        "collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("reading_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(length=1024), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "profile_id", "name", name="uq_collections_user_name"
        ),
    )
    op.create_index("ix_collections_user_id", "collections", ["user_id"])
    op.create_index("ix_collections_profile_id", "collections", ["profile_id"])
    op.create_index("ix_collection_sort_order", "collections", ["sort_order"])

    op.create_table(
        "collection_series",
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("series_key", sa.String(length=512), primary_key=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_collection_series_series",
        "collection_series",
        ["source_id", "series_key"],
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "profile_series_tags",
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
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("series_key", sa.String(length=512), primary_key=True),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("is_ai_generated", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_profile_series_tags_tag_id", "profile_series_tags", ["tag_id"]
    )

    op.create_table(
        "update_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("reading_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "followed_series_id",
            sa.Integer(),
            sa.ForeignKey("followed_series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("series_key", sa.String(length=512), nullable=False),
        sa.Column("chapter_key", sa.String(length=512), nullable=False),
        sa.Column("chapter_title", sa.String(length=512), nullable=False),
        sa.Column("chapter_number", sa.Float(), nullable=True),
        sa.Column("is_read", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_update_notifications_is_read", "update_notifications", ["is_read"]
    )
    op.create_index(
        "ix_update_notifications_created_at", "update_notifications", ["created_at"]
    )
    op.create_index(
        "ix_update_notifications_followed_series_id",
        "update_notifications",
        ["followed_series_id"],
    )
    op.create_index(
        "ix_update_notifications_user_id", "update_notifications", ["user_id"]
    )
    op.create_index(
        "ix_update_notifications_profile_id", "update_notifications", ["profile_id"]
    )

    op.create_table(
        "chapter_ocr",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("series_key", sa.String(length=512), nullable=False),
        sa.Column("chapter_key", sa.String(length=512), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("page_texts", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("engine", sa.String(length=64), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("contributed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "source_id", "series_key", "chapter_key", name="uq_chapter_ocr"
        ),
    )
    op.create_index(
        "ix_chapter_ocr_series", "chapter_ocr", ["source_id", "series_key"]
    )

    op.create_table(
        "source_series_cache",
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("series_key", sa.String(length=512), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("cover_url", sa.String(length=1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("artist", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("content_rating", sa.String(length=32), nullable=True),
        sa.Column("genres", sa.Text(), nullable=True),
        sa.Column("chapters", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )

    # --- FTS5 over chapter_ocr.full_text (external content) -----------------
    op.execute(
        """
        CREATE VIRTUAL TABLE chapter_ocr_fts USING fts5(
            full_text,
            content = 'chapter_ocr',
            content_rowid = 'id',
            tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER chapter_ocr_fts_ai AFTER INSERT ON chapter_ocr BEGIN
            INSERT INTO chapter_ocr_fts(rowid, full_text)
            VALUES (new.id, new.full_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER chapter_ocr_fts_ad AFTER DELETE ON chapter_ocr BEGIN
            INSERT INTO chapter_ocr_fts(chapter_ocr_fts, rowid, full_text)
            VALUES ('delete', old.id, old.full_text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER chapter_ocr_fts_au AFTER UPDATE ON chapter_ocr BEGIN
            INSERT INTO chapter_ocr_fts(chapter_ocr_fts, rowid, full_text)
            VALUES ('delete', old.id, old.full_text);
            INSERT INTO chapter_ocr_fts(rowid, full_text)
            VALUES (new.id, new.full_text);
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS chapter_ocr_fts_au")
    op.execute("DROP TRIGGER IF EXISTS chapter_ocr_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS chapter_ocr_fts_ai")
    op.execute("DROP TABLE IF EXISTS chapter_ocr_fts")
    for table in (
        "source_series_cache",
        "chapter_ocr",
        "update_notifications",
        "profile_series_tags",
        "tags",
        "collection_series",
        "collections",
        "reading_sessions",
        "bookmarks",
        "chapter_progress",
        "followed_series",
        "update_runs",
        "update_settings",
        "source_health",
        "source_pins",
        "reading_profiles",
        "sessions",
        "users",
    ):
        op.drop_table(table)
