from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.time_utils import utcnow


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Accounts / sessions / profiles  (kept unchanged — spec §3.1)
# ---------------------------------------------------------------------------


class User(Base):
    """An account. The first user created is the admin/owner (household model)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_username", "username"),
        # Single-admin invariant (household model): at most ONE row may have
        # is_admin=1 — the owner. The application already serializes the
        # bootstrap claim (AuthService.register, BEGIN IMMEDIATE); this partial
        # unique index is the DB-level backstop so any future lost race or new
        # code path fails loudly instead of silently minting a second owner.
        # There is deliberately no admin-promotion path in the product; if
        # co-admins ever become a feature, drop this index in that migration.
        Index(
            "uq_users_single_admin",
            "is_admin",
            unique=True,
            sqlite_where=text("is_admin = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    """An opaque bearer/cookie session. Only the SHA-256 of the token is stored;
    revocation = delete the row (per the locked auth design)."""

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_token_hash", "token_hash"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(back_populates="sessions")


class ReadingProfile(Base):
    """A per-user reading profile (Netflix-style avatars/moods)."""

    __tablename__ = "reading_profiles"
    __table_args__ = (
        Index("ix_reading_profiles_user_id", "user_id"),
        Index("ix_reading_profiles_user_sort", "user_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_key: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    mood: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mature_content_enabled: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BootstrapState(Base):
    """Singleton row (id=1): when the ``users`` table was first observed empty.

    An empty users table on a public host is an admin-takeover window — whoever
    registers first becomes admin. This timestamp bounds that window (see
    ``Settings.bootstrap_window_minutes``): uninvited bootstrap registration is
    only allowed while ``utcnow() - empty_since`` is inside the window.

    It lives in the database — not ``config/settings.json`` — deliberately: the
    window is a property of *this* database's contents, so the marker must
    travel with the DB file. A backup restore swaps the DB and the state
    follows; ``deploy.sh reset-accounts`` deletes the accounts and re-arms the
    window in the same transaction; and a stale marker can never leak in from a
    side file that outlived a wiped database. The row is deleted when the first
    account registers and (re)created the next time the table is observed empty.
    """

    __tablename__ = "bootstrap_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empty_since: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )


class SourcePin(Base):
    """A source the user pinned to the top of the Sources screen."""

    __tablename__ = "source_pins"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "profile_id", "source_id", name="uq_source_pins_user_source"
        ),
        Index("ix_source_pins_user_id", "user_id"),
        Index("ix_source_pins_profile_id", "profile_id"),
        Index("ix_source_pins_user_sort", "user_id", "profile_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class SourceHealth(Base):
    """Whether a source connector is answering, one row per connector. GLOBAL."""

    __tablename__ = "source_health"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_source_health_source_id"),
        Index("ix_source_health_consecutive_failures", "consecutive_failures"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# Update system  (kept — spec §3.1, §4.5)
# ---------------------------------------------------------------------------


class UpdateSettings(Base):
    """Global automatic update configuration (singleton row, id=1)."""

    __tablename__ = "update_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    check_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    notify_enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    check_on_startup: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class UpdateRun(Base):
    """Audit log for manual and scheduled update checks."""

    __tablename__ = "update_runs"
    __table_args__ = (Index("ix_update_runs_started_at", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    series_checked: Mapped[int] = mapped_column(Integer, default=0)
    new_chapters_found: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------------------
# Source-native library  (spec §3.2)
# ---------------------------------------------------------------------------


class FollowedSeries(Base):
    """A series is in a profile's library iff a ``followed_series`` row exists."""

    __tablename__ = "followed_series"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "profile_id",
            "source_id",
            "series_key",
            name="uq_followed_series",
        ),
        Index("ix_followed_series_library", "user_id", "profile_id", "sort_order"),
        Index("ix_followed_series_source_id", "source_id"),
        Index(
            "ix_followed_series_favorite", "user_id", "profile_id", "is_favorite"
        ),
        Index("ix_followed_series_content_rating", "content_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    series_key: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String(1024))
    is_favorite: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    reading_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="reading"
    )
    notify: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_rating: Mapped[str | None] = mapped_column(String(32))
    mature_override: Mapped[bool | None] = mapped_column(Integer)
    known_chapters: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    migrated_from_source: Mapped[str | None] = mapped_column(String(64))
    migrated_from_series_key: Mapped[str | None] = mapped_column(String(512))
    migrated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    notifications: Mapped[list[UpdateNotification]] = relationship(
        back_populates="followed_series", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Reading position / history  (spec §3.3–§3.5)
# ---------------------------------------------------------------------------


class ChapterProgress(Base):
    """Source-native reading position. Per-profile."""

    __tablename__ = "chapter_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "profile_id",
            "source_id",
            "series_key",
            "chapter_key",
            name="uq_chapter_progress",
        ),
        Index(
            "ix_chapter_progress_last_read",
            "user_id",
            "profile_id",
            "last_read_at",
        ),
        Index(
            "ix_chapter_progress_series",
            "user_id",
            "profile_id",
            "source_id",
            "series_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    series_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_number: Mapped[float | None] = mapped_column(Float)
    last_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_offset_px: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_completed: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        Index("ix_bookmarks_user_id", "user_id"),
        Index("ix_bookmarks_profile_id", "profile_id"),
        Index(
            "ix_bookmarks_series",
            "user_id",
            "profile_id",
            "source_id",
            "series_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    series_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_key: Mapped[str] = mapped_column(String(512), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReadingSession(Base):
    """One recorded stretch of reading. Per-profile, append-only.

    Read by ``services.reading_stats_service`` (the statistics screen) and
    written by ``services.progress_service``; nothing updates a row after
    insert.
    """

    __tablename__ = "reading_sessions"
    __table_args__ = (
        Index(
            "ix_reading_sessions_started_at",
            "user_id",
            "profile_id",
            "started_at",
        ),
        # The per-source / per-series roll-ups group by exactly this prefix,
        # and it is also the join key onto ``followed_series`` that resolves
        # the 18+ gate — without it every breakdown sorts the profile's whole
        # session history on a 2-vCPU box.
        Index(
            "ix_reading_sessions_series",
            "user_id",
            "profile_id",
            "source_id",
            "series_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    series_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_number: Mapped[float | None] = mapped_column(Float)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pages_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------------------
# Collections / tags  (spec §3.6–§3.7)
# ---------------------------------------------------------------------------


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "profile_id", "name", name="uq_collections_user_name"
        ),
        Index("ix_collections_user_id", "user_id"),
        Index("ix_collections_profile_id", "profile_id"),
        Index("ix_collection_sort_order", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(String(1024))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    series: Mapped[list[CollectionSeries]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class CollectionSeries(Base):
    __tablename__ = "collection_series"
    __table_args__ = (
        Index("ix_collection_series_series", "source_id", "series_key"),
    )

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    series_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    collection: Mapped[Collection] = relationship(back_populates="series")


class Tag(Base):
    """A profile's own label vocabulary.

    This used to be one global row set on the theory that "a tag is a word, not
    owned data". It is not: the name is user-authored text, and sharing the rows
    meant ``DELETE /library/tags/{id}`` destroyed a row every account read (plus
    every account's associations, via the ``profile_series_tags`` cascade), and
    ``create_tag`` handed back somebody else's row on a case-insensitive name
    collision. Owned per ``(user_id, profile_id)`` like everything else, so the
    uniqueness that used to be global is now scope-local (revision
    ``0002_tags_per_profile``).
    """

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "profile_id", "name", name="uq_tags_scope_name"),
        Index("ix_tags_scope", "user_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")
    color: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    series: Mapped[list[ProfileSeriesTag]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class ProfileSeriesTag(Base):
    __tablename__ = "profile_series_tags"
    __table_args__ = (Index("ix_profile_series_tags_tag_id", "tag_id"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    series_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    is_ai_generated: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=False
    )
    confidence: Mapped[float | None] = mapped_column(Float)

    tag: Mapped[Tag] = relationship(back_populates="series")


# ---------------------------------------------------------------------------
# Notifications  (spec §3.8)
# ---------------------------------------------------------------------------


class UpdateNotification(Base):
    """Notification emitted when a followed series gains new chapters."""

    __tablename__ = "update_notifications"
    __table_args__ = (
        Index("ix_update_notifications_is_read", "is_read"),
        Index("ix_update_notifications_created_at", "created_at"),
        Index(
            "ix_update_notifications_followed_series_id", "followed_series_id"
        ),
        Index("ix_update_notifications_user_id", "user_id"),
        Index("ix_update_notifications_profile_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=False
    )
    followed_series_id: Mapped[int] = mapped_column(
        ForeignKey("followed_series.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    series_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_title: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_number: Mapped[float | None] = mapped_column(Float)
    is_read: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    followed_series: Mapped[FollowedSeries] = relationship(
        back_populates="notifications"
    )


# ---------------------------------------------------------------------------
# OCR dialogue text  (spec §3.9 — GLOBAL, one row per chapter)
# ---------------------------------------------------------------------------


class ChapterOcr(Base):
    __tablename__ = "chapter_ocr"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "series_key", "chapter_key", name="uq_chapter_ocr"
        ),
        Index("ix_chapter_ocr_series", "source_id", "series_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    series_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_key: Mapped[str] = mapped_column(String(512), nullable=False)
    full_text: Mapped[str | None] = mapped_column(Text)
    page_texts: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16))
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contributed_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# Connector metadata cache  (spec §3.10 — GLOBAL, TTL)
# ---------------------------------------------------------------------------


class SourceSeriesCache(Base):
    __tablename__ = "source_series_cache"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    series_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    cover_url: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    artist: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(64))
    year: Mapped[int | None] = mapped_column(Integer)
    content_rating: Mapped[str | None] = mapped_column(String(32))
    genres: Mapped[str | None] = mapped_column(Text)
    chapters: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SourceBrowseCache(Base):
    """One cached browse *page* of a source's catalog (GLOBAL, TTL).

    Keyed by everything that varies the listing: ``(source_id, sort, genre,
    page)``. ``sort`` and ``genre`` store ``""`` for "not given" so they can be
    primary-key columns (SQLite PKs are NOT NULL). Search results
    (``query=...``) are deliberately NOT cached: their key cardinality is
    unbounded and each user's queries are their own.

    ``payload`` is the serialized listing exactly as the browse endpoint
    returns it (items + pagination fields), so a cache hit is a
    ``json.loads`` away from the wire. Like ``source_series_cache`` this is
    *purely* a cache — any row may be deleted at any time — and rows are
    GLOBAL: the per-caller 18+ gate is applied on every read
    (``SourceCacheService.get_browse_page``), never assumed at write time.

    Bounded: the oldest rows by ``fetched_at`` are evicted once the table
    exceeds ``settings.browse_cache_max_rows`` (hence the index).
    """

    __tablename__ = "source_browse_cache"
    __table_args__ = (Index("ix_source_browse_cache_fetched_at", "fetched_at"),)

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sort: Mapped[str] = mapped_column(String(64), primary_key=True, default="")
    genre: Mapped[str] = mapped_column(String(128), primary_key=True, default="")
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# chapter_ocr FTS5 (spec §3.12)
# ---------------------------------------------------------------------------
#
# The ``chapter_ocr_fts`` virtual table + its AI/AD/AU sync triggers are not
# ORM-mapped (SQLAlchemy has no FTS5 construct). Historically they existed only
# as raw DDL inside the Alembic baseline, so any schema built with
# ``Base.metadata.create_all()`` — every test DB, and any create_all bootstrap —
# silently lacked the OCR search index and every ``chapter_ocr_fts MATCH`` query
# raised "no such table".
#
# The ``after_create`` hook below closes that gap: create_all now emits the same
# DDL Alembic does, so both schema paths produce an identical, working index.
# ``IF NOT EXISTS`` keeps it a no-op when Alembic (or a re-run) already built it.

CHAPTER_OCR_FTS_DDL: tuple[str, ...] = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chapter_ocr_fts USING fts5(
        full_text,
        content = 'chapter_ocr',
        content_rowid = 'id',
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chapter_ocr_fts_ai AFTER INSERT ON chapter_ocr BEGIN
        INSERT INTO chapter_ocr_fts(rowid, full_text) VALUES (new.id, new.full_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chapter_ocr_fts_ad AFTER DELETE ON chapter_ocr BEGIN
        INSERT INTO chapter_ocr_fts(chapter_ocr_fts, rowid, full_text)
        VALUES ('delete', old.id, old.full_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chapter_ocr_fts_au AFTER UPDATE ON chapter_ocr BEGIN
        INSERT INTO chapter_ocr_fts(chapter_ocr_fts, rowid, full_text)
        VALUES ('delete', old.id, old.full_text);
        INSERT INTO chapter_ocr_fts(rowid, full_text) VALUES (new.id, new.full_text);
    END
    """,
)


@event.listens_for(Base.metadata, "after_create")
def _create_chapter_ocr_fts(target, connection, **kw) -> None:  # noqa: ARG001
    """Emit the ``chapter_ocr_fts`` DDL after ``create_all`` builds the tables.

    FTS5 is SQLite-only; on any other dialect this is a no-op. The ``chapter_ocr``
    table must exist first — it always does here because it is part of the same
    metadata being created, but guard anyway for a partial ``create_all(tables=…)``.
    """
    if connection.dialect.name != "sqlite":
        return
    created = {t.name for t in kw.get("tables", target.sorted_tables)}
    if "chapter_ocr" not in created:
        return
    from sqlalchemy import text as _text

    for stmt in CHAPTER_OCR_FTS_DDL:
        connection.execute(_text(stmt))
