"""Madara WordPress theme HTML parsers (parameterized by site config)."""

from __future__ import annotations

import html
import re
from typing import Any

from connectors.madara.config import MadaraSiteConfig
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SORT_TO_ORDER: dict[str, str] = {
    "default": "latest",
    "latest": "new-manga",
    "popular": "views",
    "rating": "ratings",
}


class MadaraHtml:
    """Parse one Madara site's HTML into normalized connector models."""

    def __init__(self, config: MadaraSiteConfig) -> None:
        self._cfg = config
        seg = config.url_segment
        self._seg = seg
        self._browse_card_split = re.compile(r'(?=<div class="page-item-detail)', re.I)
        self._search_card_split = re.compile(
            r'(?=<div class="row c-tabs-item__content")', re.I
        )
        self._card_anchor = re.compile(
            rf'<a href="https?://[^"]+/{seg}/([^"/]+)/"[^>]*title="([^"]*)"',
            re.I,
        )
        self._card_anchor_rel = re.compile(
            rf'<a href="/{seg}/([^"/]+)/"[^>]*title="([^"]*)"',
            re.I,
        )
        self._card_anchor_loose = re.compile(
            rf'href="(?:https?://[^"]+)?/{seg}/([a-z0-9-]+)/"[^>]*>([^<{{]+)',
            re.I,
        )
        self._card_img_tag = re.compile(r"<img\b[^>]*>", re.I)
        self._chapter_link = re.compile(
            r'<li class="wp-manga-chapter[^"]*">\s*'
            rf'<a href="https?://[^"]+/{seg}/([^"]+)/">\s*([^<]+)</a>',
            re.S | re.I,
        )
        self._chapter_img_tag = re.compile(
            r"<img\b[^>]*wp-manga-chapter-img[^>]*>", re.I
        )
        self._img_data_src = re.compile(r'data-src="\s*([^"]+?)\s*"', re.I)
        self._img_src = re.compile(r'(?<!-)\bsrc="\s*([^"]+?)\s*"', re.I)
        self._preloaded_images = re.compile(
            r"chapter_preloaded_images\s*=\s*\[(.*?)\];", re.S
        )
        self._preloaded_url = re.compile(r"'(https?://[^']+)'")
        self._reading_content_img = re.compile(
            r'<div class="reading-content">(.*?)</div>',
            re.S | re.I,
        )
        self._plain_img_src = re.compile(
            r'<img\b[^>]+src="\s*(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
            re.I,
        )
        self._listing_page_re = re.compile(rf"/{seg}/page/(\d+)/")

    def normalize_sort(self, sort: str | None) -> str:
        if not sort or sort == "default":
            return SORT_TO_ORDER["default"]
        return SORT_TO_ORDER.get(sort, sort)

    def series_id_to_path(self, series_id: str) -> str:
        return f"/{self._seg}/{series_id.strip().strip('/')}/"

    def chapter_id_to_path(self, chapter_id: str) -> str:
        return f"/{self._seg}/{chapter_id.strip().strip('/')}/"

    @staticmethod
    def make_page_id(chapter_id: str, page_number: int) -> str:
        return f"{chapter_id}:{page_number}"

    @staticmethod
    def page_id_chapter_id(page_id: str) -> str | None:
        if ":" not in page_id:
            return None
        chapter_id, _, _page_number = page_id.rpartition(":")
        return chapter_id or None

    def listing_path(self, page: int) -> str:
        if page <= 1:
            return f"/{self._seg}/"
        return f"/{self._seg}/page/{page}/"

    def listing_params(self, *, sort: str | None = None) -> dict[str, Any]:
        order = self.normalize_sort(sort)
        if order == SORT_TO_ORDER["default"]:
            return {}
        return {"m_orderby": order}

    def search_params(self, query: str, *, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"s": query.strip(), "post_type": "wp-manga"}
        if page > 1:
            params["paged"] = page
        return params

    def parse_series_list(
        self, html_text: str, *, page: int, page_size: int | None = None
    ) -> PaginatedSeriesList:
        size = page_size or self._cfg.page_size
        items = self._parse_cards(html_text, self._browse_card_split, "page-item-detail")
        total_pages = self._extract_total_pages(html_text)
        total = total_pages * size
        if page == total_pages:
            total = (total_pages - 1) * size + len(items)
        return PaginatedSeriesList(
            items=items,
            page=page,
            page_size=size,
            total=total,
            api_has_more=page < total_pages,
        )

    def parse_search_results(
        self,
        html_text: str,
        *,
        page: int,
        query: str,
        page_size: int | None = None,
    ) -> PaginatedSeriesList:
        size = page_size or self._cfg.page_size
        items = self._parse_cards(
            html_text, self._search_card_split, "c-tabs-item__content"
        )
        if not items and query.strip():
            seen: set[str] = set()
            for series_id in re.findall(
                rf"/{self._seg}/([a-z0-9-]+)/", html_text, re.I
            ):
                if series_id in seen:
                    continue
                seen.add(series_id)
                items.append(
                    Series(
                        id=series_id,
                        title=series_id,
                        canonical_path=self.series_id_to_path(series_id),
                    )
                )
        total_pages = self._extract_total_pages(html_text)
        if total_pages <= 1:
            total = len(items)
            has_more = False
        else:
            total = total_pages * size
            has_more = page < total_pages
        return PaginatedSeriesList(
            items=items,
            page=page,
            page_size=size,
            total=total,
            api_has_more=has_more,
        )

    def parse_series_detail(self, html_text: str, series_id: str) -> Series | None:
        title_match = re.search(
            r'<div class="post-title">.*?<h1>\s*([^<]+)',
            html_text,
            re.S | re.I,
        )
        title = self._clean_text(title_match.group(1)) if title_match else ""
        if not title:
            og_title = re.search(
                r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
                html_text,
                re.I,
            )
            if og_title is None:
                return None
            title = self._clean_text(og_title.group(1))
        if not title:
            return None

        cover_match = re.search(
            r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
            html_text,
            re.I,
        )
        if cover_match is None:
            cover_match = re.search(
                r'<div class="summary_image">.*?<img[^>]+src="\s*([^"]+?)\s*"',
                html_text,
                re.S | re.I,
            )
        cover_url = cover_match.group(1).strip() if cover_match else None

        status_match = re.search(
            r'<h5>\s*Status\s*</h5>\s*</div>\s*<div class="summary-content">\s*([^<]+)',
            html_text,
            re.S | re.I,
        )
        status = self._clean_text(status_match.group(1)) if status_match else None

        genres_block = re.search(
            r'<div class="genres-content">(.*?)</div>',
            html_text,
            re.S | re.I,
        )
        genres = (
            tuple(
                self._clean_text(name)
                for name in re.findall(
                    r"<a[^>]*>([^<]+)</a>", genres_block.group(1), re.S | re.I
                )
            )
            if genres_block
            else ()
        )

        author_match = re.search(
            r'<h5>\s*Author(?:\(s\)|)\s*</h5>\s*</div>\s*<div class="summary-content">.*?<a[^>]*>([^<]+)</a>',
            html_text,
            re.S | re.I,
        )
        artist_match = re.search(
            r'<h5>\s*Artist(?:\(s\)|)\s*</h5>\s*</div>\s*<div class="summary-content">.*?<a[^>]*>([^<]+)</a>',
            html_text,
            re.S | re.I,
        )
        description_match = re.search(
            r'<div class="summary__content[^"]*">(.*?)</div>',
            html_text,
            re.S | re.I,
        )

        return Series(
            id=series_id,
            title=title,
            cover_url=cover_url,
            canonical_path=self.series_id_to_path(series_id),
            description=self._clean_text(
                re.sub(r"<[^>]+>", " ", description_match.group(1))
            )
            if description_match
            else None,
            author=self._clean_text(author_match.group(1)) if author_match else None,
            artist=self._clean_text(artist_match.group(1)) if artist_match else None,
            status=status,
            genres=genres,
        )

    def parse_chapters(self, html_text: str, series_id: str) -> list[Chapter]:
        prefix = f"{series_id}/"
        chapters: list[Chapter] = []
        seen: set[str] = set()
        for chapter_id, title in self._chapter_link.findall(html_text):
            if not chapter_id.startswith(prefix):
                continue
            if chapter_id in seen:
                continue
            seen.add(chapter_id)
            number = self.parse_chapter_number(chapter_id)
            normalized_title = (
                normalize_chapter_title(self._clean_text(title))
                or self._clean_text(title)
            )
            chapters.append(
                Chapter(
                    id=chapter_id,
                    series_id=series_id,
                    title=normalized_title,
                    number=number,
                    page_count=0,
                )
            )
        chapters.sort(key=lambda ch: self.chapter_id_sort_key(ch.id))
        return chapters

    def parse_chapter_pages(self, html_text: str, chapter_id: str) -> list[Page]:
        image_urls: list[str] = []
        for tag in self._chapter_img_tag.findall(html_text):
            url = self._extract_image_url(tag)
            if url and url not in image_urls:
                image_urls.append(url)

        if not image_urls:
            for body in self._preloaded_images.findall(html_text):
                for url in self._preloaded_url.findall(body):
                    cleaned = url.strip()
                    if cleaned and cleaned not in image_urls:
                        image_urls.append(cleaned)

        if not image_urls:
            block = self._reading_content_img.search(html_text)
            if block:
                for url in self._plain_img_src.findall(block.group(1)):
                    cleaned = url.strip()
                    if cleaned and cleaned not in image_urls:
                        image_urls.append(cleaned)

        pages: list[Page] = []
        for index, remote_url in enumerate(image_urls, start=1):
            pages.append(
                Page(
                    id=self.make_page_id(chapter_id, index),
                    chapter_id=chapter_id,
                    number=index,
                    remote_url=remote_url,
                )
            )
        return pages

    def parse_chapter_number(self, chapter_id: str) -> float | None:
        if "/" not in chapter_id:
            return None
        _, segment = chapter_id.rsplit("/", 1)
        return self.parse_chapter_segment(segment)

    def parse_chapter_segment(self, segment: str) -> float | None:
        parts = self._parse_chapter_segment_parts(segment)
        if parts is None:
            return None
        major, minor, _part = parts
        if minor:
            return float(f"{major}.{minor}")
        return float(major)

    def chapter_id_sort_key(self, chapter_id: str) -> tuple[int, int, int]:
        if "/" not in chapter_id:
            return (2**31 - 1, 2**31 - 1, 2**31 - 1)
        _, segment = chapter_id.rsplit("/", 1)
        parts = self._parse_chapter_segment_parts(segment)
        if parts is None:
            return (2**31 - 1, 2**31 - 1, 2**31 - 1)
        return parts

    def _parse_chapter_segment_parts(self, segment: str) -> tuple[int, int, int] | None:
        value = segment.strip().strip("/")
        if not value.startswith("chapter-"):
            return None
        body = value.removeprefix("chapter-")
        match = re.fullmatch(r"(\d+)(?:-(\d+))?(?:_(\d+))?", body)
        if not match:
            return None
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) is not None else 0
        part = int(match.group(3)) if match.group(3) is not None else 0
        return (major, minor, part)

    def _clean_text(self, value: str) -> str:
        return html.unescape(re.sub(r"\s+", " ", value)).strip()

    def _extract_total_pages(self, html_text: str) -> int:
        pages = [int(value) for value in self._listing_page_re.findall(html_text)]
        if pages:
            return max(pages)
        if 'class="next page-numbers"' in html_text or 'class="next"' in html_text:
            return 2
        return 1

    def _extract_image_url(self, tag: str) -> str | None:
        for pattern in (self._img_data_src, self._img_src):
            match = pattern.search(tag)
            if match:
                url = match.group(1).strip()
                if url.startswith("http"):
                    return url
        return None

    def _card_cover_url(self, segment: str) -> str | None:
        for tag in self._card_img_tag.findall(segment):
            url = self._extract_image_url(tag)
            if url:
                return url
        return None

    def _parse_cards(
        self, html_text: str, split_re: re.Pattern[str], marker: str
    ) -> list[Series]:
        items: list[Series] = []
        seen: set[str] = set()
        for segment in split_re.split(html_text):
            if marker not in segment[:80]:
                continue
            anchor = (
                self._card_anchor.search(segment)
                or self._card_anchor_rel.search(segment)
                or self._card_anchor_loose.search(segment)
            )
            if anchor is None:
                continue
            slug, title = anchor.group(1), anchor.group(2)
            if slug in seen:
                continue
            seen.add(slug)
            items.append(
                Series(
                    id=slug,
                    title=self._clean_text(title),
                    cover_url=self._card_cover_url(segment),
                    canonical_path=self.series_id_to_path(slug),
                )
            )
        return items
