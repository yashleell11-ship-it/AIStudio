"""Map MangaHub's GraphQL payloads to normalized connector models.

MangaHub (https://mangahub.io) is a React app in front of a public GraphQL
API at ``https://api.mghcdn.com/graphql``. The API is fully introspectable and
every stage this connector needs is ONE query:

* ``search(...)``   -> catalog listing *and* keyword search, with a total
  ``count`` so pagination never needs a probe request;
* ``genreManga(...)`` -> the same shape, filtered to one genre;
* ``manga(slug)``   -> series metadata **and the complete chapter list** in a
  single response (``chapters { id number title slug date }``), which is why
  ``get_series``/``get_chapters`` share one fetch through a TTL cache;
* ``chapter(slug, number)`` -> every page filename of a chapter in one shot
  (``pages`` is a JSON string), so a chapter costs one request no matter how
  many images it has.

Access rules, measured from the VPS (2026-09-04):

* The endpoint 404s without ``Origin: https://mangahub.io`` and serves a
  Cloudflare interstitial without a browser ``User-Agent``. With both, the
  metadata queries need nothing else -- no cookie, no token, no bootstrap.
* Only ``chapter`` is gated: it needs an ``x-mhub-access`` value, which on the
  site is a per-pageview nonce the SSR response drops as the ``mhub_access``
  cookie. Each nonce is worth four ``chapter`` calls and never recovers.
  See ``connector.py`` for how that budget is handled.
"""

from __future__ import annotations

import json
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://mangahub.io"
API_BASE = "https://api.mghcdn.com"
GRAPHQL_PATH = "/graphql"

#: Page images and cover thumbnails. Both are subdomains of ``mghcdn.com``,
#: which is what ``allowed_image_hosts`` allowlists.
IMAGE_BASE = "https://imgx.mghcdn.com/"
THUMB_BASE = "https://thumb.mghcdn.com/"

#: The ``MangaSource`` enum member for mangahub.io itself. The site's own
#: client bundle hardcodes ``"m01"``; the sibling values are the other mirrors
#: this backend serves (``m02`` is the unfiltered adult catalog) and several of
#: the legacy ones (``mh``, ``mr``, ``mn``) now raise "table doesn't exist".
MANGA_SOURCE = "m01"

#: The site's own directory renders 24 cards per page.
PAGE_SIZE = 24

#: Fields selected from ``MangaListItem`` (search / genreManga rows).
LIST_FIELDS = (
    "id rank title slug status image latestChapter genres author isSafe "
    "updatedDate createdDate"
)

#: Fields selected from ``MangaFull`` -- detail *and* the whole chapter list.
DETAIL_FIELDS = (
    "id title alternativeTitle slug mainSlug status image latestChapter genres "
    "author artist isWebtoon isYaoi isPorn isSoftPorn isSafe description "
    "createdDate updatedDate chapters{id number title slug date}"
)

#: Fields selected from ``ChapterFullType``.
CHAPTER_FIELDS = "id mangaID number title slug date pages s"

#: App browse mode -> the API's ``SearchMod`` enum.
SORT_TO_MOD: dict[str, str] = {
    "default": "POPULAR",
    "popular": "POPULAR",
    "latest": "LATEST",
    "updated": "LATEST",
    "new": "NEW",
    "alphabetical": "ALPHABET",
    "completed": "COMPLETED",
}

BROWSE_MODES: tuple[BrowseMode, ...] = (
    BrowseMode(id="default", label="Popular"),
    BrowseMode(id="latest", label="Latest Updates"),
    BrowseMode(id="new", label="Newly Added"),
    BrowseMode(id="alphabetical", label="A-Z"),
    BrowseMode(id="completed", label="Completed"),
)


def normalize_sort(sort: str | None) -> str:
    """Map an app sort id onto a ``SearchMod`` the API accepts."""
    if not sort:
        return SORT_TO_MOD["default"]
    return SORT_TO_MOD.get(sort, SORT_TO_MOD["default"])


# --- identity ---------------------------------------------------------------
#
# ``series_key`` is MangaHub's own slug ("solo-leveling_105") -- opaque, stored
# and passed raw. ``chapter_key`` has to carry both the series slug and the
# chapter number because the API addresses a chapter by that pair, so it is
# composed here as "<series_key>/<number>" and split back with a single
# ``rpartition`` -- any slash inside the slug survives untouched.


def normalize_series_key(value: str) -> str:
    """Accept a bare slug, a ``manga/<slug>`` ref, or a full series URL."""
    cleaned = value.strip()
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
        cleaned = cleaned.split("/", 1)[1] if "/" in cleaned else ""
    cleaned = cleaned.strip("/")
    for prefix in ("manga/", "chapter/"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned


def format_chapter_number(number: float | int) -> str:
    """Render a chapter number the way the API's ``Float`` argument wants it.

    Integral numbers must not gain a ``.0`` -- ``chapter(number: 1.0)`` is
    accepted but the key it produces has to round-trip through the reader's
    URLs, so ``1`` and ``200.5`` are the canonical forms.
    """
    value = float(number)
    if value.is_integer():
        return str(int(value))
    return repr(value)


def make_chapter_key(series_key: str, number: float | int) -> str:
    return f"{series_key}/{format_chapter_number(number)}"


def split_chapter_key(chapter_key: str) -> tuple[str, float] | None:
    """Split ``"<series_key>/<number>"`` back into its two halves."""
    series_key, separator, raw_number = chapter_key.strip().rpartition("/")
    if not separator or not series_key:
        return None
    try:
        return normalize_series_key(series_key), float(raw_number)
    except ValueError:
        return None


def make_page_id(chapter_key: str, page_number: int) -> str:
    return f"{chapter_key}:{page_number}"


def page_id_chapter_key(page_id: str) -> str | None:
    chapter_key, separator, _page_number = page_id.rpartition(":")
    if not separator:
        return None
    return chapter_key or None


def series_canonical_path(series_key: str) -> str:
    return f"/manga/{series_key}"


# --- query builders ---------------------------------------------------------


def _gql_string(value: str) -> str:
    """Quote a Python string as a GraphQL string literal.

    GraphQL string escaping is a subset of JSON's, so ``json.dumps`` produces a
    literal the server accepts -- and, critically, escapes the quotes and
    backslashes a user could type into the search box.
    """
    return json.dumps(value, ensure_ascii=False)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def search_query(
    query: str,
    *,
    limit: int,
    offset: int,
    mod: str,
    hide_nsfw: bool = True,
    hide_yaoi: bool = True,
) -> str:
    return (
        "{search("
        f"x:{MANGA_SOURCE},mod:{mod},q:{_gql_string(query)},"
        f"limit:{int(limit)},offset:{int(offset)},count:true,"
        f"hideNSFW:{_bool(hide_nsfw)},hideYaoi:{_bool(hide_yaoi)}"
        ")"
        f"{{count rows{{{LIST_FIELDS}}}}}}}"
    )


def genre_manga_query(
    genre: str,
    *,
    limit: int,
    offset: int,
    mod: str,
    hide_nsfw: bool = True,
    hide_yaoi: bool = True,
) -> str:
    return (
        "{genreManga("
        f"x:{MANGA_SOURCE},mod:{mod},genre:{_gql_string(genre)},"
        f"limit:{int(limit)},offset:{int(offset)},count:true,"
        f"hideNSFW:{_bool(hide_nsfw)},hideYaoi:{_bool(hide_yaoi)}"
        ")"
        f"{{count genre{{id slug title}} rows{{{LIST_FIELDS}}}}}}}"
    )


def manga_query(series_key: str) -> str:
    return (
        f"{{manga(x:{MANGA_SOURCE},slug:{_gql_string(series_key)})"
        f"{{{DETAIL_FIELDS}}}}}"
    )


def chapter_query(series_key: str, number: float | int) -> str:
    return (
        f"{{chapter(x:{MANGA_SOURCE},slug:{_gql_string(series_key)},"
        f"number:{format_chapter_number(number)})"
        f"{{{CHAPTER_FIELDS}}}}}"
    )


def genres_query() -> str:
    return "{genres{id slug title count group}}"


# --- response helpers -------------------------------------------------------


def graphql_errors(payload: dict[str, Any]) -> list[str]:
    """The ``errors[].message`` strings of a GraphQL response, if any.

    The API answers HTTP 200 for *everything* -- a missing series, a burnt
    access nonce and a genuine server fault all arrive as 200 with a null
    ``data`` field and an ``errors`` array, so the status code carries no
    information and every failure has to be read out of the body.
    """
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return []
    messages: list[str] = []
    for error in errors:
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                messages.append(message)
    return messages


def is_rate_limited(payload: dict[str, Any]) -> bool:
    """True when the ``chapter`` query rejected the access nonce as spent."""
    return any("rate limit" in message.lower() for message in graphql_errors(payload))


def _node(payload: dict[str, Any], field: str) -> dict[str, Any] | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    node = data.get(field)
    return node if isinstance(node, dict) else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _cover_url(image: Any) -> str | None:
    """Turn a stored cover path (``"mh/solo-leveling.jpg"``) into a URL."""
    path = _text(image)
    if path is None:
        return None
    if path.startswith(("http://", "https://")):
        return path
    return THUMB_BASE + path.lstrip("/")


def _genres(value: Any) -> tuple[str, ...]:
    text = _text(value)
    if text is None:
        return ()
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _status(value: Any) -> str | None:
    text = _text(value)
    return text.capitalize() if text else None


def _latest_chapter_label(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return f"Chapter {format_chapter_number(value)}"


def _series_from_row(row: dict[str, Any]) -> Series | None:
    series_key = _text(row.get("slug"))
    title = _text(row.get("title"))
    if series_key is None or title is None:
        return None
    return Series(
        id=series_key,
        title=title,
        canonical_path=series_canonical_path(series_key),
        cover_url=_cover_url(row.get("image")),
        author=_text(row.get("author")),
        status=_status(row.get("status")),
        genres=_genres(row.get("genres")),
        latest_chapter=_latest_chapter_label(row.get("latestChapter")),
    )


def _listing_from_node(
    node: dict[str, Any] | None,
    *,
    page: int,
    page_size: int,
) -> PaginatedSeriesList:
    rows = (node or {}).get("rows")
    items: list[Series] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            series = _series_from_row(row)
            if series is not None:
                items.append(series)
    raw_total = (node or {}).get("count")
    total = int(raw_total) if isinstance(raw_total, int) else 0
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        # ``count`` is the exact catalog size, so has_more is derivable from it
        # and never needs the "did the next page come back empty?" probe.
        api_has_more=None if total > 0 else (len(items) >= page_size),
    )


def parse_series_list(
    payload: dict[str, Any],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    return _listing_from_node(_node(payload, "search"), page=page, page_size=page_size)


def parse_genre_series_list(
    payload: dict[str, Any],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    return _listing_from_node(
        _node(payload, "genreManga"), page=page, page_size=page_size
    )


def parse_chapters(payload: dict[str, Any], series_key: str) -> list[Chapter]:
    """Chapter list out of a ``manga`` response, oldest first."""
    manga = _node(payload, "manga")
    if manga is None:
        return []
    rows = manga.get("chapters")
    if not isinstance(rows, list):
        return []
    chapters: list[Chapter] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_number = row.get("number")
        if not isinstance(raw_number, (int, float)) or isinstance(raw_number, bool):
            continue
        number = float(raw_number)
        label = format_chapter_number(number)
        # Older MangaHub rows carry an empty title; the site renders those as
        # plain "Chapter N", so do the same rather than showing a blank row.
        title = _text(row.get("title")) or f"Chapter {label}"
        chapters.append(
            Chapter(
                id=make_chapter_key(series_key, number),
                series_id=series_key,
                title=title,
                number=number,
                page_count=0,
                release_date=_text(row.get("date")),
            )
        )
    chapters.sort(key=lambda chapter: (chapter.number or 0.0))
    return chapters


def parse_series_detail(payload: dict[str, Any], series_key: str) -> Series | None:
    manga = _node(payload, "manga")
    if manga is None:
        return None
    title = _text(manga.get("title"))
    if title is None:
        return None
    key = _text(manga.get("slug")) or series_key
    chapters = parse_chapters(payload, key)
    latest = chapters[-1].title if chapters else _latest_chapter_label(
        manga.get("latestChapter")
    )
    return Series(
        id=key,
        title=title,
        chapter_count=len(chapters),
        canonical_path=series_canonical_path(key),
        description=_text(manga.get("description")),
        cover_url=_cover_url(manga.get("image")),
        author=_text(manga.get("author")),
        artist=_text(manga.get("artist")),
        status=_status(manga.get("status")),
        genres=_genres(manga.get("genres")),
        latest_chapter=latest,
    )


def parse_chapter_pages(payload: dict[str, Any], chapter_key: str) -> list[Page]:
    """Page images out of a ``chapter`` response.

    ``pages`` is a JSON *string* of the form
    ``{"p": "<directory>/", "i": ["1.jpg", "2.jpg", ...]}``. The directory is
    authoritative and must be used verbatim: aliased series (``demon-town-
    museum`` serving ``the-spirit-suppressing-museum/47/``) and mixed file
    extensions (``.jpg`` vs ``.webp``) both make a synthesized URL wrong.
    """
    chapter = _node(payload, "chapter")
    if chapter is None:
        return []
    raw_pages = chapter.get("pages")
    if not isinstance(raw_pages, str) or not raw_pages.strip():
        return []
    try:
        decoded = json.loads(raw_pages)
    except (ValueError, TypeError):
        return []
    if not isinstance(decoded, dict):
        return []
    directory = decoded.get("p")
    names = decoded.get("i")
    if not isinstance(directory, str) or not isinstance(names, list):
        return []
    prefix = directory.lstrip("/")
    pages: list[Page] = []
    for index, name in enumerate(names, start=1):
        if not isinstance(name, str) or not name.strip():
            continue
        pages.append(
            Page(
                id=make_page_id(chapter_key, index),
                chapter_id=chapter_key,
                number=index,
                remote_url=IMAGE_BASE + prefix + name.strip().lstrip("/"),
            )
        )
    return pages


def parse_genres(payload: dict[str, Any]) -> list[BrowseMode]:
    data = payload.get("data")
    rows = data.get("genres") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    modes: list[BrowseMode] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        slug = _text(row.get("slug"))
        title = _text(row.get("title"))
        if slug is None or title is None or slug in seen:
            continue
        seen.add(slug)
        modes.append(BrowseMode(id=slug, label=title))
    return modes
