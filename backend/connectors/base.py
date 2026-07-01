"""Base interface for pluggable content sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series


class SourceConnector(ABC):
    """Abstract connector for discovering series, chapters, and pages."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Stable identifier for this connector implementation."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the Sources UI."""

    @property
    def description(self) -> str:
        """Optional description for the Sources UI."""
        return ""

    @property
    def is_browsable(self) -> bool:
        """Whether this connector appears in the online Sources browser."""
        return True

    @property
    def supports_import(self) -> bool:
        """Whether this connector can import content into the local library."""
        return False

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        """Domain suffixes this connector may proxy images/covers from.

        Empty by default — connectors that proxy remote images (page images,
        cover art) over HTTP(S) MUST override this with the exact CDN domains
        they legitimately serve from. This is enforced by the image proxy
        (``BrowseService._fetch_url``) as an SSRF allowlist: any URL whose
        host does not match one of these domains (or a subdomain of one) is
        rejected before a request is made.
        """
        return frozenset()

    def list_browse_modes(self) -> list[BrowseMode]:
        """Return catalog views this connector supports (popular, latest, etc.)."""
        return [BrowseMode(id="default", label="Browse")]

    @abstractmethod
    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        """Return a paginated list of series available from this source."""

    @abstractmethod
    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        """Search series on this source. Must not query the local library."""

    @abstractmethod
    def get_series(self, series_id: str) -> Series | None:
        """Return metadata for a single series."""

    @abstractmethod
    def get_chapters(self, series_id: str) -> list[Chapter]:
        """Return all chapters for a series."""

    @abstractmethod
    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        """Return all pages for a chapter."""

    def find_page(self, page_id: str) -> Page | None:
        """Locate a page by ID. Every connector that serves images MUST override this.
        The default is intentionally unimplemented — O(series × chapters × pages) API
        calls per image proxy request is catastrophic in production."""
        raise NotImplementedError(
            f"{type(self).__name__} must override find_page(). "
            "The default traversal is O(n³) and is never acceptable."
        )
