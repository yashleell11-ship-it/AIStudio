"""Normalized content objects returned by every source connector."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Page:
    """A single readable page independent of its origin."""

    id: str
    chapter_id: str
    number: int
    file_path: str | None = None
    archive_path: str | None = None
    archive_member: str | None = None
    remote_url: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class Chapter:
    """A chapter belonging to a series."""

    id: str
    series_id: str
    title: str
    number: float | None
    page_count: int
    folder_path: str | None = None
    archive_path: str | None = None
    release_date: str | None = None


@dataclass(frozen=True, slots=True)
class Series:
    """A series independent of its origin."""

    id: str
    title: str
    chapter_count: int = 0
    canonical_path: str | None = None
    description: str | None = None
    cover_url: str | None = None
    author: str | None = None
    artist: str | None = None
    status: str | None = None
    genres: tuple[str, ...] = ()
    latest_chapter: str | None = None


@dataclass(frozen=True, slots=True)
class BrowseMode:
    """A catalog view supported by a source connector (e.g. popular, latest)."""

    id: str
    label: str


@dataclass(frozen=True, slots=True)
class PaginatedSeriesList:
    """Paginated series listing."""

    items: list[Series] = field(default_factory=list)
    page: int = 1
    page_size: int = 50
    total: int = 0
    api_has_more: bool | None = None

    @property
    def has_more(self) -> bool:
        if self.api_has_more is not None:
            return self.api_has_more
        if self.total <= 0:
            return False
        consumed = (self.page - 1) * self.page_size + len(self.items)
        return consumed < self.total

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 1
        return max(1, (self.total + self.page_size - 1) // self.page_size)
