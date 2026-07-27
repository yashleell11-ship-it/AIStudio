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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.time_utils import utcnow


class Base(DeclarativeBase):
    pass


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    series: Mapped[list[Series]] = relationship(back_populates="library")


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (
        UniqueConstraint("folder_path", name="uq_series_folder_path"),
        Index("ix_series_library_id", "library_id"),
        Index("ix_series_title", "title"),
        Index("ix_series_sort_title", "sort_title"),
        Index("ix_series_reading_status", "reading_status"),
        Index("ix_series_is_favorite", "is_favorite"),
        Index("ix_series_updated_at", "updated_at"),
        Index("ix_series_live", "library_id", "sort_title"),
        # Production: compound indexes for filtered queries
        Index("ix_series_status_sort", "status", "sort_title"),
        Index("ix_series_author_sort", "author", "sort_title"),
        Index("ix_series_language_sort", "language", "sort_title"),
        Index("ix_series_year_sort", "year"),
        Index("ix_series_created_at", "created_at"),
        Index("ix_series_content_rating", "content_rating"),
        Index("ix_series_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(64))
    cover_path: Mapped[str | None] = mapped_column(String(1024))
    folder_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Library Intelligence fields
    sort_title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    original_title: Mapped[str | None] = mapped_column(String(512))
    artist: Mapped[str | None] = mapped_column(String(255))
    content_rating: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ko")
    year: Mapped[int | None] = mapped_column(Integer)
    is_favorite: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    reading_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unread")
    total_chapters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    read_chapters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_created: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    library: Mapped[Library] = relationship(back_populates="series")
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="series", order_by="Chapter.number"
    )
    reading_progress: Mapped[ReadingProgress | None] = relationship(
        back_populates="series", uselist=False
    )
    bookmarks: Mapped[list[Bookmark]] = relationship(back_populates="series")
    collections: Mapped[list[CollectionSeries]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    tags: Mapped[list[SeriesTag]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("series_id", "folder_path", name="uq_chapter_series_folder"),
        Index("ix_chapters_series_id", "series_id"),
        Index("ix_chapters_folder_path", "folder_path"),
        # Production indexes for read tracking and sort
        Index("ix_chapters_series_sort", "series_id", "sort_key"),
        Index("ix_chapters_is_read", "is_read"),
        Index("ix_chapters_read_at", "read_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    volume_id: Mapped[int | None] = mapped_column(ForeignKey("volumes.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    number: Mapped[float | None] = mapped_column(Float)
    folder_path: Mapped[str | None] = mapped_column(String(1024))
    archive_path: Mapped[str | None] = mapped_column(String(1024))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    cover_path: Mapped[str | None] = mapped_column(String(1024))
    # Library Intelligence fields
    sort_key: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    is_read: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime)

    series: Mapped[Series] = relationship(back_populates="chapters")
    pages: Mapped[list[Page]] = relationship(
        back_populates="chapter", order_by="Page.number"
    )
    ocr_jobs: Mapped[list[OcrJob]] = relationship(
        back_populates="chapter", order_by="OcrJob.created_at"
    )
    chapter_text: Mapped[ChapterText | None] = relationship(
        back_populates="chapter", uselist=False
    )


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (Index("ix_volumes_series_id", "series_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    number: Mapped[int | None] = mapped_column(Integer)
    cover_path: Mapped[str | None] = mapped_column(String(1024))


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (Index("ix_pages_chapter_id", "chapter_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)

    chapter: Mapped[Chapter] = relationship(back_populates="pages")
    page_text: Mapped[PageText | None] = relationship(
        back_populates="page", uselist=False
    )


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    __table_args__ = (
        # Per-profile: one progress row per (user, profile, series). Nullable
        # user_id/profile_id for legacy rows (claimed/backfilled on migration).
        UniqueConstraint(
            "user_id", "profile_id", "series_id", name="uq_reading_progress_user_series"
        ),
        Index("ix_reading_progress_series_id", "series_id"),
        Index("ix_reading_progress_user_id", "user_id"),
        Index("ix_reading_progress_profile_id", "profile_id"),
        # Production: powers "continue reading" strip and activity feeds
        Index("ix_reading_progress_last_read", "last_read_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    last_page: Mapped[int] = mapped_column(Integer, default=1)
    # Library Intelligence fields
    scroll_offset_px: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    series: Mapped[Series] = relationship(back_populates="reading_progress")
    chapter: Mapped[Chapter] = relationship()


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        Index("ix_bookmarks_series_id", "series_id"),
        Index("ix_bookmarks_user_id", "user_id"),
        Index("ix_bookmarks_profile_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    # Library Intelligence field
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    series: Mapped[Series] = relationship(back_populates="bookmarks")
    chapter: Mapped[Chapter] = relationship()
    page_ref: Mapped[Page | None] = relationship()


class ImportHistory(Base):
    __tablename__ = "import_history"
    __table_args__ = (Index("ix_import_history_library_id", "library_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    library_id: Mapped[int | None] = mapped_column(ForeignKey("libraries.id"))
    folder_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    series_count: Mapped[int] = mapped_column(Integer, default=0)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Download(Base):
    __tablename__ = "downloads"
    __table_args__ = (
        Index("ix_downloads_source_series_chapter", "source", "series_id", "chapter_id"),
        Index("ix_downloads_status", "status"),
        Index("ix_downloads_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Who queued this download. Background workers read ownership off the row
    # (they have no request/user context). Nullable for legacy rows.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    series_id: Mapped[str] = mapped_column(String(128), nullable=False)
    chapter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    series_title: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    pages_total: Mapped[int] = mapped_column(Integer, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    local_chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
    error: Mapped[str | None] = mapped_column(Text)

    queue: Mapped[DownloadQueue | None] = relationship(
        back_populates="download", uselist=False
    )


class DownloadQueue(Base):
    __tablename__ = "download_queue"
    __table_args__ = (Index("ix_download_queue_state_priority", "state", "priority"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    download_id: Mapped[int] = mapped_column(
        ForeignKey("downloads.id"), nullable=False, unique=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    download: Mapped[Download] = relationship(back_populates="queue")


class SourceChapterLink(Base):
    """Maps an external source chapter to a local library chapter."""

    __tablename__ = "source_chapter_links"
    __table_args__ = (
        UniqueConstraint("source", "series_id", "chapter_id", name="uq_source_chapter"),
        Index("ix_source_chapter_links_local", "local_chapter_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    series_id: Mapped[str] = mapped_column(String(128), nullable=False)
    chapter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    local_chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        # Per-profile: collection names are unique within a (user, profile).
        UniqueConstraint(
            "user_id", "profile_id", "name", name="uq_collections_user_name"
        ),
        Index("ix_collections_user_id", "user_id"),
        Index("ix_collections_profile_id", "profile_id"),
        # Production: fast ordering for collection grid
        Index("ix_collection_sort_order", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_path: Mapped[str | None] = mapped_column(String(1024))
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
        Index("ix_collection_series_series_id", "series_id"),
    )

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id"), primary_key=True
    )
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id"), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    collection: Mapped[Collection] = relationship(back_populates="series")
    series: Mapped[Series] = relationship(back_populates="collections")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")
    color: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    series: Mapped[list[SeriesTag]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class SeriesTag(Base):
    __tablename__ = "series_tags"
    __table_args__ = (
        Index("ix_series_tags_tag_id", "tag_id"),
    )

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id"), primary_key=True
    )
    is_ai_generated: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(Float)

    series: Mapped[Series] = relationship(back_populates="tags")
    tag: Mapped[Tag] = relationship(back_populates="series")


class ChapterProgress(Base):
    __tablename__ = "chapter_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "profile_id", "chapter_id", name="uq_chapter_progress_user_chapter"
        ),
        Index("ix_chapter_progress_chapter_id", "chapter_id"),
        Index("ix_chapter_progress_user_id", "user_id"),
        Index("ix_chapter_progress_profile_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id"), nullable=False
    )
    last_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scroll_offset_px: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_completed: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    chapter: Mapped[Chapter] = relationship()


class ReadingSession(Base):
    __tablename__ = "reading_sessions"
    __table_args__ = (
        Index("ix_reading_sessions_series_id", "series_id"),
        Index("ix_reading_sessions_chapter_id", "chapter_id"),
        Index("ix_reading_sessions_started_at", "started_at"),
        Index("ix_reading_sessions_user_id", "user_id"),
        Index("ix_reading_sessions_profile_id", "profile_id"),
        # Production: compound index for history aggregation and per-series lookups
        Index("ix_reading_sessions_started_series", "started_at", "series_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id"), nullable=False
    )
    start_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pages_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)

    series: Mapped[Series] = relationship()
    chapter: Mapped[Chapter] = relationship()


class OcrJob(Base):
    """Tracks OCR processing jobs for chapters."""

    __tablename__ = "ocr_jobs"
    __table_args__ = (
        Index("ix_ocr_jobs_chapter_id", "chapter_id"),
        Index("ix_ocr_jobs_status", "status"),
        Index("ix_ocr_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued"
    )  # queued, processing, completed, failed, cancelled
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="tesseract")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    pages_total: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    chapter: Mapped[Chapter] = relationship(back_populates="ocr_jobs")


class PageText(Base):
    """Extracted text and bounding boxes for a single page."""

    __tablename__ = "page_texts"
    __table_args__ = (
        UniqueConstraint("page_id", name="uq_page_texts_page_id"),
        Index("ix_page_texts_page_id", "page_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    boxes: Mapped[str | None] = mapped_column(Text)  # JSON array of bounding boxes
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="tesseract")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    page: Mapped[Page] = relationship(back_populates="page_text")


class ChapterText(Base):
    """Aggregated full-text for a chapter, enabling search and future AI features."""

    __tablename__ = "chapter_texts"
    __table_args__ = (
        UniqueConstraint("chapter_id", name="uq_chapter_texts_chapter_id"),
        Index("ix_chapter_texts_chapter_id", "chapter_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    full_text: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str | None] = mapped_column(String(16))
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="tesseract")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    chapter: Mapped[Chapter] = relationship(back_populates="chapter_text")


class UpdateSettings(Base):
    """Global automatic update configuration (singleton row, id=1)."""

    __tablename__ = "update_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    notify_enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    auto_download_enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    check_on_startup: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class SeriesTracker(Base):
    """Tracks a remote series for new chapter detection (followed or downloaded)."""

    __tablename__ = "series_trackers"
    __table_args__ = (
        # Per-profile follow: two profiles (even on one account) may each follow
        # the same remote series independently.
        UniqueConstraint(
            "user_id", "profile_id", "source", "series_id", "track_kind",
            name="uq_series_tracker",
        ),
        Index("ix_series_trackers_source", "source"),
        Index("ix_series_trackers_enabled", "enabled"),
        Index("ix_series_trackers_track_kind", "track_kind"),
        Index("ix_series_trackers_user_id", "user_id"),
        Index("ix_series_trackers_profile_id", "profile_id"),
        # The 18+ gate filters by resolved rating on every tracker read.
        Index("ix_series_trackers_content_rating", "content_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Owner of this follow/tracker. Background scheduler reads it off the row.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    series_id: Mapped[str] = mapped_column(String(128), nullable=False)
    series_title: Mapped[str] = mapped_column(String(512), nullable=False)
    track_kind: Mapped[str] = mapped_column(String(32), nullable=False)  # followed | downloaded
    local_series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"))
    enabled: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    notify: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    auto_download: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    check_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    known_chapter_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Same catalog as known_chapter_ids but keeping each chapter's NUMBER:
    # ``[{"id": ..., "number": ...}]``. Numbers are the only stable axis across
    # sources (ids are opaque per-source strings, titles are translations), so
    # without this a migration off a source that has since died has nothing to
    # map progress by. known_chapter_ids is kept until a later contract
    # migration so the update engine's diff is unchanged.
    known_chapters: Mapped[str | None] = mapped_column(Text)
    # --- maturity, resolved by core.content_rating.resolve_tracker_rating ----
    # Captured at follow time from the connector's genres; NULL means "no
    # signal", which resolves to unknown rather than to safe.
    content_rating: Mapped[str | None] = mapped_column(String(64))
    # The user's explicit verdict. Wins over everything, including the source's
    # own maturity — the only mechanism that works for the many dead connectors
    # where no metadata will ever arrive again.
    mature_override: Mapped[bool | None] = mapped_column(Integer)
    # --- source-migration audit trail ---------------------------------------
    # Kept so a bad repoint stays diagnosable (and undoable) while the old ids
    # are still known; the migration itself overwrites source/series_id.
    migrated_from_source: Mapped[str | None] = mapped_column(String(64))
    migrated_from_series_id: Mapped[str | None] = mapped_column(String(128))
    migrated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    notifications: Mapped[list[UpdateNotification]] = relationship(
        back_populates="tracker", cascade="all, delete-orphan"
    )


class UpdateNotification(Base):
    """Notification emitted when a tracked series gains new chapters."""

    __tablename__ = "update_notifications"
    __table_args__ = (
        Index("ix_update_notifications_is_read", "is_read"),
        Index("ix_update_notifications_created_at", "created_at"),
        Index("ix_update_notifications_tracker_id", "tracker_id"),
        Index("ix_update_notifications_user_id", "user_id"),
        Index("ix_update_notifications_profile_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Denormalised owner (inherited from the tracker) so notification lists can
    # scope by user/profile without a join, and workers can set it off the
    # tracker row.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    tracker_id: Mapped[int] = mapped_column(ForeignKey("series_trackers.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    series_id: Mapped[str] = mapped_column(String(128), nullable=False)
    series_title: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    chapter_title: Mapped[str] = mapped_column(String(512), nullable=False)
    chapter_number: Mapped[int | None] = mapped_column(Integer)
    is_read: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    tracker: Mapped[SeriesTracker] = relationship(back_populates="notifications")


class UpdateRun(Base):
    """Audit log for manual and scheduled update checks."""

    __tablename__ = "update_runs"
    __table_args__ = (Index("ix_update_runs_started_at", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)  # manual | scheduled | startup
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    series_checked: Mapped[int] = mapped_column(Integer, default=0)
    new_chapters_found: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class User(Base):
    """An account. The first user created is the admin/owner (household model)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_username", "username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    # Email is optional metadata only — there is no email verification/reset flow
    # (rejected in the locked auth design).
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
    # SHA-256 hex of the opaque token; the raw token is never persisted.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(back_populates="sessions")


class ReadingProfile(Base):
    """A per-user reading profile (Netflix-style avatars/moods).

    One account can hold several lightweight profiles (a max is enforced in the
    service layer). Unlike the legacy per-user-state tables, this is a new table
    with no pre-multi-user rows, so ``user_id`` is NOT NULL and deletes cascade
    with the owning account. Profile-scoped data partitioning is a later phase;
    for now a profile is just a named, ordered, themed presence on an account.
    """

    __tablename__ = "reading_profiles"
    __table_args__ = (
        Index("ix_reading_profiles_user_id", "user_id"),
        # Powers the ordered per-user profile list.
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
    # Per-profile adult/18+ gate. Overrides the global config default for
    # discovery surfaces when this profile is the active one.
    mature_content_enabled: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserSeriesState(Base):
    """Per-(user, profile) membership and state for a catalog series.

    ``series`` rows are catalog facts with no owner, so this table — not the
    catalog — is the authority on who has what. ``in_library`` is the membership
    bit: a series is in a profile's library only if a row here says so. Library,
    Browse, Search, statistics and recommendations all filter through it, which
    is what keeps a brand-new account (or a second profile on one account) from
    seeing anything another one added.

    ``user_id`` is nullable so a pre-multi-user database can be migrated with the
    owner unknown — the first admin registration claims all NULL-owned rows (see
    AuthService.register). Supersedes the legacy ``series.is_favorite`` /
    ``series.reading_status`` / ``series.read_chapters`` columns, which remain
    until a later contract migration drops them.
    """

    __tablename__ = "user_series_state"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "profile_id", "series_id", name="uq_user_series_state"
        ),
        Index("ix_user_series_state_user", "user_id"),
        Index("ix_user_series_state_profile_id", "profile_id"),
        Index("ix_user_series_state_series", "series_id"),
        Index("ix_user_series_state_user_favorite", "user_id", "is_favorite"),
        Index("ix_user_series_state_user_status", "user_id", "reading_status"),
        # Covers the series ⋈ user_series_state join every scoped listing does:
        # (user_id, profile_id) narrows to the caller, in_library applies
        # membership, and the trailing series_id supplies the join key — SQLite
        # resolves the whole user_series_state side as a COVERING INDEX with no
        # table lookup. A bare index on the in_library boolean would be too
        # unselective for the planner to pick, and a plain
        # (user_id, profile_id, series_id) index would duplicate the index
        # SQLite already builds for uq_user_series_state.
        Index(
            "ix_user_series_state_library",
            "user_id", "profile_id", "in_library", "series_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("reading_profiles.id", ondelete="CASCADE"), nullable=True
    )
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    # Membership bit. A row may exist with in_library=False (e.g. progress was
    # recorded from Browse without adding), so presence of the row is NOT
    # membership — this column is.
    in_library: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=False, server_default="0"
    )
    is_favorite: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    reading_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unread")
    read_chapters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class SourcePin(Base):
    """A source the user pinned to the top of the Sources screen.

    Pins are server-side (not client prefs) so they follow the account across
    devices, and are scoped to (user_id, profile_id) like every other per-user
    row. ``source_id`` is the connector key (e.g. "mangadex"), not a FK —
    connectors are code, not rows, and a pin must survive a connector being
    temporarily unregistered.

    Unlike the legacy per-user-state tables this is a new table with no
    pre-multi-user rows, so ``user_id`` is NOT NULL and deletes cascade with the
    owning account — a pin can never land in the unowned bucket that
    AuthService._claim_unowned_data sweeps. ``profile_id`` stays nullable to
    match the rest of the scoped tables; uniqueness across a NULL profile_id is
    not DB-enforced (SQLite treats NULLs as distinct), so the app layer owns
    that, as it already does for series_trackers.
    """

    __tablename__ = "source_pins"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "profile_id", "source_id", name="uq_source_pins_user_source"
        ),
        Index("ix_source_pins_user_id", "user_id"),
        Index("ix_source_pins_profile_id", "profile_id"),
        # Powers the ordered pinned-section read.
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
