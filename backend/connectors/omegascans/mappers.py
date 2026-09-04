"""Map Omega Scans' Heancms JSON API onto normalized connector models.

Omega Scans (https://omegascans.org) is a Next.js front end over a Heancms
JSON API at ``https://api.omegascans.org``. Nothing is server-rendered that
the API does not already hand over in one call, so this connector talks to
the API directly and never parses HTML.

Endpoints used (all verified from the production VPS, no challenge):

* ``GET /query``                          -> catalog listing AND keyword search
* ``GET /tags``                           -> genre filter list
* ``GET /series/<series_slug>``           -> series metadata (+ numeric id)
* ``GET /chapter/query?series_id=<id>``   -> the WHOLE chapter list in one call
* ``GET /chapter/<series_slug>/<chapter_slug>`` -> every page image in one call

Identity keys are opaque strings built from the site's own slugs:

* ``series_key``  == ``<series_slug>``                       (e.g. ``sex-stopwatch``)
* ``chapter_key`` == ``<series_slug>/<chapter_slug>``        (contains a slash)
* ``page_id``     == ``<chapter_key>:<page_number>``

They are never re-parsed for meaning outside this module.
"""

from __future__ import annotations

import html
import re
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://omegascans.org"
API_BASE = "https://api.omegascans.org"

#: Series per catalog page. The API accepts any ``perPage``; 24 fills the grid.
PAGE_SIZE = 24

#: One-shot chapter fetch size. The largest series in the catalog has 270
#: chapters (``a-wonderful-new-world``, measured from the VPS), so 500 gets
#: every chapter of every series in a SINGLE request -- ``last_page`` comes
#: back as 1. ``_fetch_chapter_payloads`` still pages defensively in case the
#: catalog ever outgrows this, but in practice it never loops.
CHAPTER_FETCH_SIZE = 500

#: ``series_type=Comic`` is not just a novel filter. Without it the listing
#: inlines EVERY chapter of every series into ``free_chapters``: the same
#: 12-item page measured 275 KB with it absent and 25 KB with it present, an
#: 11x payload cut for data this connector does not read. The two ``Novel``
#: entries in the catalog are excluded as a bonus -- this is a manga source.
SERIES_TYPE = "Comic"

#: Site's own ``<select>`` values for ``orderBy``. ``latest`` orders by most
#: recent chapter release, ``created_at`` by when the series was added.
SORT_TO_ORDER: dict[str, tuple[str, str]] = {
    "default": ("latest", "desc"),      # Latest Updates -- the reader's home view
    "latest": ("latest", "desc"),
    "popular": ("total_views", "desc"),
    "added": ("created_at", "desc"),
    "alphabetical": ("title", "asc"),
    "rating": ("rating", "desc"),
}

BROWSE_MODES: tuple[BrowseMode, ...] = (
    BrowseMode(id="default", label="Latest Updates"),
    BrowseMode(id="popular", label="Popular"),
    BrowseMode(id="added", label="Recently Added"),
    BrowseMode(id="rating", label="Top Rated"),
    BrowseMode(id="alphabetical", label="A-Z"),
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
#: Chapter names on this source are uniform: a survey of 1285 chapters across
#: 25 randomly sampled series from the VPS found 1285/1285 matching
#: ``Chapter N`` or ``Chapter N.5``. The slug (``chapter-27-5``) is the
#: fallback for anything that ever deviates.
_NAME_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
_SLUG_NUMBER_RE = re.compile(r"(\d+(?:[.-]\d+)?)\s*$")


def normalize_sort(sort: str | None) -> tuple[str, str]:
    """Return the ``(orderBy, order)`` pair for an app-level sort id."""
    if not sort:
        return SORT_TO_ORDER["default"]
    return SORT_TO_ORDER.get(sort, SORT_TO_ORDER["default"])


def clean_text(value: Any) -> str:
    """Strip tags, decode entities, collapse whitespace."""
    if value is None:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def series_path(series_key: str) -> str:
    return f"/series/{series_key.strip().strip('/')}"


def chapter_path(chapter_key: str) -> str:
    return f"/chapter/{chapter_key.strip().strip('/')}"


def make_chapter_key(series_key: str, chapter_slug: str) -> str:
    return f"{series_key.strip('/')}/{str(chapter_slug).strip('/')}"


def chapter_key_series(chapter_key: str) -> str | None:
    """The series half of a chapter key, or None when it is malformed."""
    series_key, _, chapter_slug = chapter_key.strip("/").partition("/")
    if not series_key or not chapter_slug:
        return None
    return series_key


def make_page_id(chapter_key: str, page_number: int) -> str:
    return f"{chapter_key}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    """Recover the chapter key from a page id.

    ``rpartition`` (not ``partition``) because the chapter key itself carries
    a slash and could in principle carry a colon; only the LAST colon is the
    page-number separator this module wrote.
    """
    if ":" not in page_id:
        return None
    chapter_key, _, _number = page_id.rpartition(":")
    return chapter_key or None


def parse_chapter_number(chapter_name: str | None, chapter_slug: str | None) -> float | None:
    """The site's own chapter number as a stable float."""
    for candidate, pattern in ((chapter_name, _NAME_NUMBER_RE), (chapter_slug, _SLUG_NUMBER_RE)):
        if not candidate:
            continue
        match = pattern.search(str(candidate))
        if match is None:
            continue
        try:
            return float(match.group(1).replace("-", "."))
        except ValueError:
            continue
    return None


def listing_params(
    *,
    page: int,
    sort: str | None = None,
    query: str = "",
    tag_id: str | None = None,
) -> dict[str, Any]:
    """Query string for ``/query`` -- one endpoint serves browse AND search."""
    order_by, order = normalize_sort(sort)
    params: dict[str, Any] = {
        "query_string": query.strip(),
        "series_status": "All",
        "order": order,
        "orderBy": order_by,
        "series_type": SERIES_TYPE,
        "page": max(int(page), 1),
        "perPage": PAGE_SIZE,
        "tags_ids": f"[{tag_id}]" if tag_id else "[]",
        # Omega Scans is an adult scanlation group; without this the API hides
        # most of its own catalog from an anonymous client.
        "adult": "true",
    }
    return params


def chapter_list_params(series_numeric_id: int, *, page: int = 1) -> dict[str, Any]:
    return {
        "page": max(int(page), 1),
        "perPage": CHAPTER_FETCH_SIZE,
        "series_id": int(series_numeric_id),
    }


def _series_from_item(item: dict[str, Any]) -> Series | None:
    series_key = str(item.get("series_slug") or "").strip("/")
    title = clean_text(item.get("title"))
    if not series_key or not title:
        return None

    # ``free_chapters`` is capped at the 5 most recent by ``series_type=Comic``
    # (see SERIES_TYPE) -- enough for the card's "latest chapter" line and
    # already paid for, so it costs no extra request.
    latest_chapter: str | None = None
    free_chapters = item.get("free_chapters")
    if isinstance(free_chapters, list) and free_chapters:
        first = free_chapters[0]
        if isinstance(first, dict):
            latest_chapter = clean_text(first.get("chapter_name")) or None

    chapter_count = 0
    meta = item.get("meta")
    if isinstance(meta, dict):
        try:
            chapter_count = int(str(meta.get("chapters_count") or 0))
        except (TypeError, ValueError):
            chapter_count = 0

    return Series(
        id=series_key,
        title=title,
        chapter_count=chapter_count,
        canonical_path=series_path(series_key),
        description=clean_text(item.get("description")) or None,
        cover_url=str(item.get("thumbnail") or "") or None,
        status=clean_text(item.get("status")) or None,
        latest_chapter=latest_chapter,
    )


def parse_series_list(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    data = payload.get("data")
    items: list[Series] = []
    seen: set[str] = set()
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            series = _series_from_item(item)
            if series is None or series.id in seen:
                continue
            seen.add(series.id)
            items.append(series)

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    try:
        total = int(meta.get("total") or 0)
    except (TypeError, ValueError):
        total = len(items)
    try:
        last_page = int(meta.get("last_page") or 1)
    except (TypeError, ValueError):
        last_page = 1

    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        api_has_more=page < last_page,
    )


def series_numeric_ids(payload: dict[str, Any]) -> dict[str, int]:
    """slug -> numeric id for every item in a listing response.

    The chapter-list endpoint only accepts the NUMERIC series id (passing the
    slug answers HTTP 500), and every listing already carries it. Harvesting
    the mapping here is what lets ``get_chapters`` skip the detail request
    for any series the user reached from a browse or search page.
    """
    mapping: dict[str, int] = {}
    data = payload.get("data")
    if not isinstance(data, list):
        return mapping
    for item in data:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("series_slug") or "").strip("/")
        raw_id = item.get("id")
        if not slug or raw_id is None:
            continue
        try:
            mapping[slug] = int(raw_id)
        except (TypeError, ValueError):
            continue
    return mapping


def parse_series_detail(payload: dict[str, Any], series_key: str) -> tuple[Series | None, int | None]:
    """Return ``(series, numeric_id)`` from a ``/series/<slug>`` response."""
    title = clean_text(payload.get("title"))
    if not title:
        return None, None

    numeric_id: int | None
    try:
        numeric_id = int(payload["id"])
    except (KeyError, TypeError, ValueError):
        numeric_id = None

    genres: tuple[str, ...] = ()
    tags = payload.get("tags")
    if isinstance(tags, list):
        genres = tuple(
            name
            for name in (clean_text(tag.get("name")) for tag in tags if isinstance(tag, dict))
            if name
        )

    chapter_count = 0
    meta = payload.get("meta")
    if isinstance(meta, dict):
        try:
            chapter_count = int(str(meta.get("chapters_count") or 0))
        except (TypeError, ValueError):
            chapter_count = 0

    series = Series(
        id=series_key,
        title=title,
        chapter_count=chapter_count,
        canonical_path=series_path(series_key),
        description=clean_text(payload.get("description")) or None,
        cover_url=str(payload.get("thumbnail") or "") or None,
        author=clean_text(payload.get("author")) or None,
        # The API has no ``artist`` field; ``studio`` is the production studio
        # credited for the art and is the closest true equivalent.
        artist=clean_text(payload.get("studio")) or None,
        status=clean_text(payload.get("status")) or None,
        genres=genres,
    )
    return series, numeric_id


def parse_chapters(payloads: list[dict[str, Any]], series_key: str) -> list[Chapter]:
    """Flatten one or more ``/chapter/query`` pages into ordered chapters.

    Chapters with ``price > 0`` are dropped: the reader endpoint answers
    ``{"paywall": true}`` with no ``chapter_data`` for those, so listing them
    would put unreadable entries in the chapter list. They reappear on their
    own once the site flips them free (``free_at``).
    """
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for payload in payloads:
        data = payload.get("data")
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            chapter_slug = str(item.get("chapter_slug") or "").strip("/")
            if not chapter_slug:
                continue
            try:
                price = float(item.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            if price > 0:
                continue
            chapter_key = make_chapter_key(series_key, chapter_slug)
            if chapter_key in seen:
                continue
            seen.add(chapter_key)

            name = clean_text(item.get("chapter_name")) or chapter_slug
            subtitle = clean_text(item.get("chapter_title"))
            title = f"{name} - {subtitle}" if subtitle and subtitle != name else name

            chapters.append(
                Chapter(
                    id=chapter_key,
                    series_id=series_key,
                    title=title,
                    number=parse_chapter_number(name, chapter_slug),
                    # The chapter-list endpoint carries no page count; the
                    # connector backfills it from its page cache once a
                    # chapter has actually been opened.
                    page_count=0,
                    release_date=str(item.get("created_at") or "") or None,
                )
            )

    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0, chapter.id))
    return chapters


def chapter_list_last_page(payload: dict[str, Any]) -> int:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return 1
    try:
        return max(int(meta.get("last_page") or 1), 1)
    except (TypeError, ValueError):
        return 1


def parse_chapter_pages(payload: dict[str, Any], chapter_key: str) -> list[Page]:
    """Every page image for one chapter, from one response.

    ``chapter_data.images`` is a plain ordered list of absolute CDN URLs, so
    resolving a chapter's images costs exactly ONE request no matter how many
    pages it has -- there is no per-page round trip to make.
    """
    if payload.get("paywall"):
        return []
    chapter = payload.get("chapter")
    if not isinstance(chapter, dict):
        return []
    chapter_data = chapter.get("chapter_data")
    if not isinstance(chapter_data, dict):
        return []
    images = chapter_data.get("images")
    if not isinstance(images, list):
        return []

    pages: list[Page] = []
    for index, raw_url in enumerate(images, start=1):
        url = str(raw_url or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        pages.append(
            Page(
                id=make_page_id(chapter_key, len(pages) + 1),
                chapter_id=chapter_key,
                number=len(pages) + 1,
                remote_url=url,
            )
        )
    return pages


def parse_tags(payload: Any) -> list[BrowseMode]:
    """``/tags`` -> genre filters. The API returns a bare JSON array."""
    if not isinstance(payload, list):
        return []
    modes: list[BrowseMode] = []
    for tag in payload:
        if not isinstance(tag, dict):
            continue
        name = clean_text(tag.get("name"))
        tag_id = tag.get("id")
        if not name or tag_id is None:
            continue
        modes.append(BrowseMode(id=str(tag_id), label=name))
    modes.sort(key=lambda mode: mode.label.lower())
    return modes
