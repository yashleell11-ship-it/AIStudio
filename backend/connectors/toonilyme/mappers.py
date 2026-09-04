"""Map toonily.me (ToonTop) JSON API payloads to normalized connector models.

``toonily.me`` 301-redirects to ``https://toontop.io`` -- the site was
rebranded, and the canonical origin is the one used here so no request pays a
redirect hop. Despite the domain family it is NOT a Toonily/Madara clone: it
is a Next.js front end over a documented-looking JSON API at
``https://api.toontop.io``, so this connector parses JSON, never HTML.

Endpoints (all verified from the production VPS):

* ``GET /titles/search``                              -> browse, search, genre
* ``GET /titles/by-slug/<slug>?include=details``      -> series detail (+ hsid)
* ``GET /titles/<hsid>/chapters``                     -> the WHOLE chapter list
* ``GET /titles/by-slug/<slug>/chapters/<ch>?include=details`` -> page images

Every response is a ``{"success": bool, "data": {...}}`` envelope.
"""

from __future__ import annotations

import re
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://toontop.io"
API_BASE = "https://api.toontop.io"

#: The API's own default page size for ``/titles/search`` and what the site
#: itself requests. ``limit`` is validated upstream as 1..500.
PAGE_SIZE = 24

SEARCH_PATH = "/titles/search"

# The image CDN (rx.toontop.io) enforces hotlink protection: an image GET with
# no Referer answers 403 with an HTML body, so both the proxy and the download
# pipeline must send the site Referer. Verified from the VPS.
IMAGE_HOST = "toontop.io"

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# The API rejects any `sort` outside this set with a 400 that names the whole
# vocabulary: newest, rating, views, popular, bookmarks, chapters, comments,
# latest, added_date, views_today, views_7days, views_30days. Only the modes
# below are exposed; there is no alphabetical sort upstream, so none is
# advertised rather than silently returning a different order.
SORT_TO_API: dict[str, str] = {
    "default": "latest",
    "latest": "latest",
    "popular": "popular",
    "rating": "rating",
    "trending": "views_7days",
    "new": "added_date",
}


def normalize_sort(sort: str | None) -> str:
    if not sort:
        return SORT_TO_API["default"]
    return SORT_TO_API.get(sort, SORT_TO_API["default"])


def browse_modes() -> list[BrowseMode]:
    return [
        BrowseMode(id="default", label="Latest Updates"),
        BrowseMode(id="popular", label="Popular"),
        BrowseMode(id="trending", label="Trending This Week"),
        BrowseMode(id="rating", label="Top Rated"),
        BrowseMode(id="new", label="Recently Added"),
    ]


#: Captured from the site's own genre index on the VPS (71 genres). Held as a
#: constant so ``list_genres`` costs zero requests -- the set changes about as
#: often as the site is redesigned, and a stale entry degrades to an empty
#: result page rather than an error.
GENRES: tuple[tuple[str, str], ...] = (
    ("action", "Action"), ("adult", "Adult"), ("adventure", "Adventure"),
    ("age-gap", "Age Gap"), ("all-ages", "All Ages"), ("bdsm", "BDSM"),
    ("bl", "BL"), ("campus", "Campus"), ("comedy", "Comedy"),
    ("comics", "Comics"), ("cooking", "Cooking"), ("crime", "Crime"),
    ("demons", "Demons"), ("doujins-original-series", "Doujins- Original Series"),
    ("doujinshi", "Doujinshi"), ("drama", "Drama"), ("ecchi", "Ecchi"),
    ("family", "Family"), ("fantasy", "Fantasy"), ("female-friend", "Female Friend"),
    ("fetish", "Fetish"), ("gender-bender", "Gender Bender"),
    ("girls-lacrosse-club", "Girls Lacrosse Club"), ("gl", "GL"),
    ("gossip", "Gossip"), ("harem", "Harem"), ("hentai", "Hentai"),
    ("hentai-manga", "Hentai Manga"), ("historical", "Historical"),
    ("horror", "Horror"), ("incest", "Incest"), ("isekai", "Isekai"),
    ("josei", "Josei"), ("kimi-no-na-wa", "Kimi no na wa"), ("magic", "Magic"),
    ("manga", "Manga"), ("manhwa", "Manhwa"), ("manhwa-hentai", "Manhwa Hentai"),
    ("martial-arts", "Martial Arts"), ("mature", "Mature"), ("milf", "Milf"),
    ("military", "Military"), ("monster-girls", "Monster Girls"),
    ("mystery", "Mystery"), ("ntr", "NTR"), ("office", "Office"),
    ("office-workers", "Office Workers"), ("original-work", "Original Work"),
    ("psychological", "Psychological"), ("rape", "Rape"), ("raw", "Raw"),
    ("reincarnation", "Reincarnation"), ("revenge", "Revenge"),
    ("romance", "Romance"), ("school-life", "School life"), ("sci-fi", "Sci-Fi"),
    ("secret-relationship", "Secret Relationship"), ("seinen", "Seinen"),
    ("shoujo", "Shoujo"), ("shounen", "Shounen"), ("slice-of-life", "Slice of Life"),
    ("smut", "Smut"), ("sports", "Sports"), ("supernatural", "Supernatural"),
    ("thriller", "Thriller"), ("tragedy", "Tragedy"), ("uncensored", "Uncensored"),
    ("vanilla", "Vanilla"), ("webtoon", "Webtoon"), ("yaoi", "Yaoi"), ("yuri", "Yuri"),
)


def genre_modes() -> list[BrowseMode]:
    return [BrowseMode(id=slug, label=label) for slug, label in GENRES]


# --------------------------------------------------------------------------
# Identity keys
# --------------------------------------------------------------------------
# series_key  = "<series-slug>"                  e.g. "lookism"
# chapter_key = "<series-slug>/<chapter-slug>"   e.g. "lookism/chapter-623"
# page_id     = "<chapter_key>:<n>"              e.g. "lookism/chapter-623:1"
#
# These mirror the site's own URL paths, so they stay valid across the site's
# internal hash-id churn (the ``id``/hsid fields are NOT stable identifiers to
# persist -- they are opaque per-deploy handles).


def normalize_series_key(value: str) -> str:
    """Reduce anything series-shaped to the bare slug."""
    cleaned = (value or "").strip().strip("/")
    # Accept a full path or URL ("https://toontop.io/lookism", "/lookism").
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
        cleaned = cleaned.split("/", 1)[1] if "/" in cleaned else ""
    return cleaned.split("/", 1)[0].split("?", 1)[0]


def make_chapter_key(series_key: str, chapter_slug: str) -> str:
    return f"{series_key}/{chapter_slug}"


def split_chapter_key(chapter_key: str) -> tuple[str, str] | None:
    """Split this connector's OWN chapter key back into its two slugs.

    The key is opaque to the rest of the app; only this module, which minted
    it, may take it apart.
    """
    cleaned = (chapter_key or "").strip().strip("/")
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
        cleaned = cleaned.split("/", 1)[1] if "/" in cleaned else ""
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def make_page_id(chapter_key: str, page_number: int) -> str:
    return f"{chapter_key}:{page_number}"


def page_id_chapter_key(page_id: str) -> str | None:
    chapter_key, sep, _number = (page_id or "").rpartition(":")
    if not sep or not chapter_key:
        return None
    return chapter_key


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def series_detail_path(series_key: str) -> str:
    return f"/titles/by-slug/{series_key}"


def chapter_list_path(hsid: str) -> str:
    return f"/titles/{hsid}/chapters"


def chapter_detail_path(series_key: str, chapter_slug: str) -> str:
    return f"/titles/by-slug/{series_key}/chapters/{chapter_slug}"


def search_params(
    query: str | None,
    page: int,
    *,
    sort: str | None = None,
    genre: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "page": max(1, page),
        "limit": PAGE_SIZE,
        "sort": normalize_sort(sort),
    }
    if query:
        params["q"] = query
    if genre:
        params["genres"] = genre
    return params


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

_CHAPTER_NUMBER_IN_NAME = re.compile(r"(\d+(?:\.\d+)?)")
_CHAPTER_NUMBER_IN_SLUG = re.compile(r"^chapter-(\d+)(?:-(\d+))?$", re.I)


def unwrap(payload: Any) -> dict[str, Any]:
    """Return the ``data`` object from the API envelope.

    A failed call still answers with ``{"success": false, ...}`` and an HTTP
    error status, so the caller sees a ``ConnectorHttpError``; this only has
    to cope with a success body whose shape drifted.
    """
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def parse_chapter_number(name: str, slug: str) -> float | None:
    """The site's own chapter number.

    Read from the DISPLAY name first ("Chapter 200.5" -> 200.5), because the
    payload's ``number`` field is an internal ordering sequence, not the
    published number: Lookism's "Chapter 623" carries ``number: 634``. Using
    it would renumber every series that ever had a bonus chapter inserted.
    The slug ("chapter-200-5") is the fallback for an unnamed chapter.
    """
    if name:
        match = _CHAPTER_NUMBER_IN_NAME.search(name)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    match = _CHAPTER_NUMBER_IN_SLUG.match((slug or "").strip())
    if match:
        whole, frac = match.group(1), match.group(2)
        try:
            return float(f"{whole}.{frac}") if frac else float(whole)
        except ValueError:
            return None
    return None


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _names(values: Any) -> str | None:
    """Join a list of ``{"name": ...}`` objects (authors, artists)."""
    if not isinstance(values, list):
        return None
    names = [n for n in (_text(v.get("name")) for v in values if isinstance(v, dict)) if n]
    return ", ".join(names) or None


def _genres(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(
        n for n in (_text(v.get("name")) for v in values if isinstance(v, dict)) if n
    )


def _series_from_item(item: dict[str, Any]) -> Series | None:
    """Build a Series from a search/browse list item."""
    slug = _text(item.get("slug"))
    title = _text(item.get("name"))
    if not slug or not title:
        return None
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    latest = item.get("latest_chapters")
    latest_name = None
    if isinstance(latest, list) and latest and isinstance(latest[0], dict):
        latest_name = _text(latest[0].get("name"))
    chapter_count = stats.get("chapters_count")
    return Series(
        id=slug,
        title=title,
        chapter_count=int(chapter_count) if isinstance(chapter_count, int) else 0,
        description=_text(item.get("summary")),
        cover_url=_text(item.get("cover")),
        author=_names(item.get("authors")),
        artist=_names(item.get("artists")),
        status=_text(item.get("status")),
        genres=_genres(item.get("genres")),
        latest_chapter=latest_name,
    )


def parse_series_list(payload: Any, page: int) -> PaginatedSeriesList:
    data = unwrap(payload)
    raw_items = data.get("items")
    items: list[Series] = []
    if isinstance(raw_items, list):
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            series = _series_from_item(entry)
            if series is not None:
                items.append(series)

    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    total = pagination.get("total")
    has_next = pagination.get("has_next")
    limit = pagination.get("limit")
    return PaginatedSeriesList(
        items=items,
        page=max(1, page),
        page_size=int(limit) if isinstance(limit, int) and limit > 0 else PAGE_SIZE,
        total=int(total) if isinstance(total, int) and total >= 0 else len(items),
        api_has_more=bool(has_next) if isinstance(has_next, bool) else None,
    )


def parse_series_detail(payload: Any, series_key: str) -> Series | None:
    data = unwrap(payload)
    title = data.get("title")
    if not isinstance(title, dict):
        return None
    name = _text(title.get("name"))
    if not name:
        return None
    stats = title.get("stats") if isinstance(title.get("stats"), dict) else {}
    chapter_count = stats.get("chapters_count")
    latest = title.get("latest_chapters")
    latest_name = None
    if isinstance(latest, list) and latest and isinstance(latest[0], dict):
        latest_name = _text(latest[0].get("name"))
    return Series(
        id=series_key,
        title=name,
        chapter_count=int(chapter_count) if isinstance(chapter_count, int) else 0,
        description=_text(title.get("summary")),
        cover_url=_text(title.get("cover")),
        author=_names(title.get("authors")),
        artist=_names(title.get("artists")),
        status=_text(title.get("status")),
        genres=_genres(title.get("genres")),
        latest_chapter=latest_name,
    )


def series_hsid(payload: Any) -> str | None:
    """The per-deploy handle needed by the bulk chapter-list endpoint."""
    title = unwrap(payload).get("title")
    if isinstance(title, dict):
        return _text(title.get("id"))
    return None


def declared_chapter_count(payload: Any) -> int:
    title = unwrap(payload).get("title")
    if not isinstance(title, dict):
        return 0
    stats = title.get("stats")
    if isinstance(stats, dict) and isinstance(stats.get("chapters_count"), int):
        return max(0, stats["chapters_count"])
    return 0


def _chapters_from_entries(entries: Any, series_key: str) -> list[Chapter]:
    if not isinstance(entries, list):
        return []
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        slug = _text(entry.get("slug"))
        if not slug or slug in seen:
            continue
        seen.add(slug)
        name = _text(entry.get("name")) or slug
        chapters.append(
            Chapter(
                id=make_chapter_key(series_key, slug),
                series_id=series_key,
                title=name,
                number=parse_chapter_number(name, slug),
                # The chapter list carries no image count; the connector
                # backfills it from cache once a chapter has been opened.
                page_count=0,
                release_date=_text(entry.get("updated_at")),
            )
        )
    # Ascending by number (last == newest), the ordering every other connector
    # here returns. Unnumbered chapters sink to the end rather than to 0.
    chapters.sort(
        key=lambda chapter: chapter.number if chapter.number is not None else float("inf")
    )
    return chapters


def parse_embedded_chapters(payload: Any, series_key: str) -> list[Chapter]:
    """Chapters carried inside the series-detail response (newest ~50)."""
    title = unwrap(payload).get("title")
    if not isinstance(title, dict):
        return []
    return _chapters_from_entries(title.get("chapters"), series_key)


def parse_chapters(payload: Any, series_key: str) -> list[Chapter]:
    """Chapters from the bulk ``/titles/<hsid>/chapters`` endpoint."""
    return _chapters_from_entries(unwrap(payload).get("chapters"), series_key)


def parse_chapter_pages(payload: Any, chapter_key: str) -> list[Page]:
    chapter = unwrap(payload).get("chapter")
    if not isinstance(chapter, dict):
        return []
    images = chapter.get("images")
    if not isinstance(images, list):
        return []
    pages: list[Page] = []
    for index, url in enumerate(images, start=1):
        cleaned = _text(url)
        if not cleaned:
            continue
        pages.append(
            Page(
                id=make_page_id(chapter_key, index),
                chapter_id=chapter_key,
                number=index,
                remote_url=cleaned,
            )
        )
    return pages
