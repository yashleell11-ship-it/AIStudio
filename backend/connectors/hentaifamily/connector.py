"""HentaiFox-family gallery source connector base."""

from __future__ import annotations

import logging

from connectors.base import SourceConnector
from connectors.hentaifamily.mappers import (
    HentaiFamilySite,
    HOME_PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    gallery_path,
    home_listing_path,
    make_page_id,
    page_id_gallery_id,
    parse_chapters,
    parse_gallery_pages_from_detail,
    parse_reader_image_url,
    parse_series_detail,
    parse_series_list,
    reader_path,
    search_listing_path,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class HentaiFamilyConnector(SourceConnector):
    """Browse and read galleries from a HentaiFox-family site."""

    SITE: HentaiFamilySite
    SOURCE_TYPE: str
    DISPLAY_NAME: str
    DESCRIPTION: str
    MATURE = True
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._site = self.SITE
        self._http = SyncConnectorHttpClient(
            self._site.site_base,
            headers=HTML_HEADERS,
            user_agent=BROWSER_USER_AGENT,
            min_interval=0.35,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._gallery_html_cache: TTLCache[str] = TTLCache(ttl_seconds=300.0)

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def is_browsable(self) -> bool:
        return self.BROWSABLE

    @property
    def supports_import(self) -> bool:
        return self.SUPPORTS_IMPORT

    @property
    def is_mature(self) -> bool:
        return self.MATURE

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        host = self._site.image_host_suffix.lstrip(".")
        return frozenset({host, f"i.{host}", f"i2.{host}", f"i3.{host}", f"m11.{host}"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{self._site.site_base}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="new", label="New"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="top_rated", label="Top Rated"),
        ]

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def _normalize_gallery_id(self, gallery_id: str) -> str:
        value = gallery_id.strip().strip("/")
        if value.startswith("gallery/"):
            value = value.removeprefix("gallery/")
        if "/" in value:
            value = value.split("/", 1)[0]
        return value

    def _listing_path(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str | None = None,
    ) -> tuple[str, int]:
        if query:
            return search_listing_path(query, page, sort=sort), SEARCH_PAGE_SIZE
        return home_listing_path(page, sort=sort), HOME_PAGE_SIZE

    def _fetch_listing(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str | None = None,
    ) -> PaginatedSeriesList:
        path, page_size = self._listing_path(page, sort=sort, query=query)
        document = self._fetch_html(path)
        return parse_series_list(document, page=page, page_size=page_size)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        listing = self._fetch_listing(page, sort=sort if sort != "latest" else None)
        logger.info(
            "%s browse page=%d count=%d has_more=%s",
            self.DISPLAY_NAME,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        listing = self._fetch_listing(
            page,
            query=normalized,
            sort=sort if sort and sort != "latest" else None,
        )
        logger.info(
            "%s search page=%d count=%d query=%r",
            self.DISPLAY_NAME,
            page,
            len(listing.items),
            normalized,
        )
        return listing

    def _gallery_document(self, gallery_id: str) -> str | None:
        cached = self._gallery_html_cache.get(gallery_id)
        if cached is not None:
            return cached
        try:
            document = self._fetch_html(gallery_path(gallery_id))
        except ConnectorHttpError:
            return None
        self._gallery_html_cache.set(gallery_id, document)
        return document

    def get_series(self, series_id: str) -> Series | None:
        gallery_id = self._normalize_gallery_id(series_id)
        cached = self._series_cache.get(gallery_id)
        if cached is not None:
            return cached
        document = self._gallery_document(gallery_id)
        if document is None:
            return None
        series = parse_series_detail(document, gallery_id=gallery_id)
        if series is None:
            return None
        self._series_cache.set(gallery_id, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        gallery_id = self._normalize_gallery_id(series_id)
        return self._chapter_list_cache.get_or_set(
            gallery_id,
            lambda: self._fetch_chapters(gallery_id),
        )

    def _fetch_chapters(self, gallery_id: str) -> list[Chapter]:
        document = self._gallery_document(gallery_id)
        if document is None:
            return []
        return parse_chapters(document, gallery_id=gallery_id)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        gallery_id = self._normalize_gallery_id(chapter_id)
        return self._page_cache.get_or_set(
            gallery_id,
            lambda: self._fetch_chapter_pages(gallery_id),
        )

    def _fetch_chapter_pages(self, gallery_id: str) -> list[Page]:
        document = self._gallery_document(gallery_id)
        if document is None:
            return []
        pages = parse_gallery_pages_from_detail(document, gallery_id=gallery_id)
        if not pages:
            return []
        self._refresh_page_urls_from_reader(gallery_id, pages)
        return pages

    def _refresh_page_urls_from_reader(self, gallery_id: str, pages: list[Page]) -> None:
        """Fix mixed webp/png extensions by reading the last page (and any mismatch)."""
        if not pages:
            return
        last = pages[-1]
        try:
            reader_html = self._fetch_html(
                reader_path(self._site, gallery_id, last.number)
            )
        except ConnectorHttpError:
            return
        image_url = parse_reader_image_url(reader_html)
        if image_url:
            pages[-1] = Page(
                id=last.id,
                chapter_id=last.chapter_id,
                number=last.number,
                remote_url=image_url,
            )

    def find_page(self, page_id: str) -> Page | None:
        gallery_id = page_id_gallery_id(page_id)
        if gallery_id is None:
            return None
        for page in self.get_chapter_pages(gallery_id):
            if page.id == page_id:
                return page
        return None


def build_hentai_family_connector(site: HentaiFamilySite) -> type[HentaiFamilyConnector]:
    """Return a connector class configured for one HentaiFox-family site."""
    description = (
        f"Browse and read hentai galleries from {site.display_name}. "
        "Images are proxied through ManhwaManiacs."
    )
    class_name = "".join(part.title() for part in site.source_id.split("_"))
    if not class_name.endswith("Connector"):
        class_name = f"{class_name}Connector"
    return type(
        class_name,
        (HentaiFamilyConnector,),
        {
            "SITE": site,
            "SOURCE_TYPE": site.source_id,
            "DISPLAY_NAME": site.display_name,
            "DESCRIPTION": description,
            "__module__": __name__,
        },
    )
