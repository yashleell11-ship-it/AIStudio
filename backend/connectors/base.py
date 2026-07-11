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
    def is_mature(self) -> bool:
        """Whether this source primarily serves adult (18+) content.

        Mature sources are hidden from the Sources browser and are not
        searchable unless the user has explicitly enabled mature content
        (``Settings.mature_content_enabled``). Set the class attribute
        ``MATURE = True`` on a connector to mark it adult -- both this
        property and the registry descriptor read that attribute, so a
        connector never needs to override this method."""
        return bool(getattr(self, "MATURE", False))

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

    def image_fetch_headers(self) -> dict[str, str]:
        """Optional headers for outbound cover/page image GETs.

        CDNs that enforce hotlink protection (e.g. Toonily's ``tnlycdn.com``)
        require a site ``Referer``. Override on connectors that need it; the
        image proxy and download pipeline merge these into every image request.
        """
        return {}

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        """Fetch an image when plain httpx is insufficient (DDoS-Guard, etc.).

        Return ``(content_type, body)`` when this connector handles the fetch
        itself; return ``None`` to let ``BrowseService`` use its default client.
        """
        return None

    def list_browse_modes(self) -> list[BrowseMode]:
        """Return catalog views this connector supports (popular, latest, etc.)."""
        return [BrowseMode(id="default", label="Browse")]

    def list_genres(self) -> list[BrowseMode]:
        """Return genre/tag filters this source supports in the browse UI."""
        return []

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        """Browse a genre-specific catalog view when the source supports it."""
        raise NotImplementedError(f"{type(self).__name__} does not support genre browse.")

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
