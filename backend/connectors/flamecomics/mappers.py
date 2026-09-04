"""Map Flame Comics' Next.js data payloads to normalized connector models.

Flame Comics (flamecomics.xyz) is a Next.js **pages-router** site. Every view
we need is statically generated, so alongside each HTML page Next.js serves the
page's props as JSON at ``/_next/data/<buildId>/<route>.json``. Probed from the
VPS (2026-09-04) those JSON routes are 10-15x smaller than the HTML that embeds
them -- ``/browse`` is 1.5 MB of HTML but 103 KB of JSON -- and they are not
under ``/api/``, which is the only path ``robots.txt`` disallows for ``*``.

Three properties of those payloads shape this connector:

* ``/browse.json`` returns the **entire catalog** in one response (166 entries
  at capture time), so browsing, sorting, genre filtering and search are all
  served from a single cached fetch rather than a request per page.
* ``/series/<id>.json`` returns the series metadata **and its full chapter
  list** together, so ``get_series`` and ``get_chapters`` share one fetch.
* ``/series/<id>/<token>.json`` returns the chapter's complete image manifest
  (name, width, height per page), so page-image resolution costs zero requests
  per page -- the URLs are built from the manifest.

Novels live in the same catalog under a ``novel_id`` key and are served from
``/novel/...`` routes; this is a manga connector, so entries without a
``series_id`` are dropped (see ``_is_comic``).
"""

from __future__ import annotations

import html as html_module
import re
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://flamecomics.xyz"
CDN_BASE = "https://cdn.flamecomics.xyz"

#: Local page size. Every listing is sliced out of one cached full-catalog
#: payload, so this is presentation only -- it never costs an extra request.
PAGE_SIZE = 30

#: Cheapest page on the site that still carries ``"buildId"`` (40 KB vs the
#: homepage's 459 KB, measured from the VPS).
BUILD_ID_PATH = "/info/about"

_BUILD_ID_RE = re.compile(r'"buildId"\s*:\s*"([^"]{1,128})"')
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

#: A ``_next/data`` request for a build that no longer exists answers 404 with
#: this body, where a genuinely missing series answers ``{"notFound":true}``.
#: Both are 404s, so the connector distinguishes them by re-resolving the
#: build id rather than by status (see ``connector._fetch_data``).
_STALE_BUILD_MARKER = "pageProps"


def parse_build_id(html: str) -> str | None:
    """Pull Next.js' ``buildId`` out of any page's ``__NEXT_DATA__`` blob.

    The build id changes on every site deploy and is a path segment of every
    JSON route, so it is resolved at runtime and cached, never hardcoded.
    """
    match = _BUILD_ID_RE.search(html or "")
    if match is None:
        return None
    build_id = match.group(1).strip()
    # A path segment: reject anything that could escape the route.
    if not build_id or "/" in build_id or "?" in build_id or "#" in build_id:
        return None
    return build_id


def build_id_path() -> str:
    return BUILD_ID_PATH


def browse_data_path(build_id: str) -> str:
    return f"/_next/data/{build_id}/browse.json"


def latest_data_path(build_id: str) -> str:
    return f"/_next/data/{build_id}/latest.json"


def series_data_path(build_id: str, series_key: str) -> str:
    return f"/_next/data/{build_id}/series/{series_key}.json"


def chapter_data_path(build_id: str, series_key: str, token: str) -> str:
    return f"/_next/data/{build_id}/series/{series_key}/{token}.json"


def series_url(series_key: str) -> str:
    return f"{SITE_BASE}/series/{series_key}"


# --------------------------------------------------------------------------
# identity keys (opaque to callers; only this module composes/decomposes them)
# --------------------------------------------------------------------------


def make_chapter_key(series_key: str, token: str) -> str:
    """``"<series_id>/<token>"`` -- the site's own chapter URL suffix.

    Flame Comics identifies a chapter by an opaque 16-hex ``token`` that is
    only meaningful under its series, and the page-image CDN path needs both
    halves, so both travel in the key. Callers treat it as an opaque string.
    """
    return f"{series_key}/{token}"


def split_chapter_key(chapter_key: str) -> tuple[str, str] | None:
    """Inverse of ``make_chapter_key``; ``None`` when the shape is wrong."""
    cleaned = (chapter_key or "").strip().strip("/")
    if cleaned.startswith("series/"):
        cleaned = cleaned[len("series/") :]
    series_key, _, token = cleaned.partition("/")
    if not series_key or not token or "/" in token:
        return None
    return series_key, token


def make_page_id(chapter_key: str, number: int) -> str:
    return f"{chapter_key}:{number}"


def page_id_chapter_key(page_id: str) -> str | None:
    """Split a page id back into its chapter key.

    Chapter keys contain a ``/`` but never a ``:``, so ``rpartition(":")`` is
    unambiguous.
    """
    if ":" not in (page_id or ""):
        return None
    chapter_key, _, number = page_id.rpartition(":")
    if not chapter_key or not number.isdigit():
        return None
    return chapter_key


def normalize_series_key(series_id: str) -> str:
    """Accept a bare id, a ``/series/<id>`` path, or a full URL."""
    value = (series_id or "").strip().strip("/")
    if value.startswith(SITE_BASE):
        value = value[len(SITE_BASE) :].strip("/")
    if value.startswith("series/"):
        value = value[len("series/") :]
    # A chapter key handed to a series call: keep the series half.
    value = value.split("/", 1)[0]
    return value.strip()


# --------------------------------------------------------------------------
# field helpers
# --------------------------------------------------------------------------


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_description(value: Any) -> str | None:
    """Flame Comics stores descriptions as Mantine-classed HTML paragraphs."""
    raw = _text(value)
    if not raw:
        return None
    # Paragraph boundaries would otherwise glue sentences together.
    spaced = re.sub(r"</p\s*>|<br\s*/?>", "\n", raw, flags=re.I)
    stripped = _HTML_TAG_RE.sub(" ", spaced)
    unescaped = html_module.unescape(stripped)
    lines = [_WS_RE.sub(" ", line).strip() for line in unescaped.split("\n")]
    text = "\n".join(line for line in lines if line).strip()
    return text or None


def _join_people(value: Any) -> str | None:
    """``author``/``artist`` arrive as lists of names."""
    if isinstance(value, str):
        return _text(value) or None
    if not isinstance(value, list):
        return None
    names = [_text(item) for item in value if _text(item)]
    return ", ".join(names) or None


def _genres(entry: dict[str, Any]) -> tuple[str, ...]:
    """``/browse`` calls them ``categories``; ``/series/<id>`` calls them ``tags``."""
    raw = entry.get("categories")
    if not isinstance(raw, list):
        raw = entry.get("tags")
    if not isinstance(raw, list):
        return ()
    seen: list[str] = []
    for item in raw:
        name = _text(item)
        if name and name not in seen:
            seen.append(name)
    return tuple(seen)


def _is_comic(entry: Any) -> bool:
    """True for a comic series, False for the novels sharing this catalog.

    Novels carry ``novel_id`` instead of ``series_id`` and live under
    ``/novel/<id>``, whose routes this connector never builds. 13 of the 166
    catalog entries were novels at capture time.
    """
    return isinstance(entry, dict) and entry.get("series_id") is not None


def _series_key_of(entry: dict[str, Any]) -> str:
    return str(entry.get("series_id"))


def cover_url(series_key: str, cover: Any, version: Any = None) -> str | None:
    """Build the CDN cover URL.

    Mirrors the site's own bundle: ``urlJoin(CDN, "/uploads/images/series/",
    id, cover)`` plus a cache-busting ``?<last_edit>``. A ``cover`` that is
    already absolute is passed through, as the site does.
    """
    name = _text(cover)
    if not name:
        return None
    if name.startswith("http://") or name.startswith("https://"):
        return name
    url = f"{CDN_BASE}/uploads/images/series/{series_key}/{name.lstrip('/')}"
    stamp = _text(version) or (str(version) if isinstance(version, int) else "")
    return f"{url}?{stamp}" if stamp else url


def page_image_url(series_key: str, token: str, name: str, version: Any = None) -> str:
    """Build a page-image CDN URL.

    Taken from the reader bundle:
    ``uploads/images/series/${series_id}/${token}/${name}?${edit_time}`` --
    note the path uses the chapter **token**, not ``chapter_id``.
    """
    url = f"{CDN_BASE}/uploads/images/series/{series_key}/{token}/{name.lstrip('/')}"
    stamp = _text(version) or (str(version) if isinstance(version, int) else "")
    return f"{url}?{stamp}" if stamp else url


def parse_chapter_number(value: Any) -> float | None:
    """``chapter`` arrives as the site's own decimal string, e.g. ``"14.00"``."""
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value)
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _release_date(value: Any) -> str | None:
    """Release dates are unix seconds; keep them as a plain string."""
    if isinstance(value, (int, float)) and value > 0:
        return str(int(value))
    text = _text(value)
    return text or None


def _chapter_display_title(entry: dict[str, Any], number: float | None) -> str:
    raw = entry.get("title") if entry.get("title") is not None else entry.get("chapter_title")
    title = normalize_chapter_title(_text(raw))
    if number is not None:
        label = f"{number:g}"
        return f"Chapter {label}" + (f" - {title}" if title else "")
    return title or "Chapter"


# --------------------------------------------------------------------------
# listings
# --------------------------------------------------------------------------

#: Browse modes. ``default``/``popular``/``new``/``alphabetical`` are all
#: served from ONE cached catalog payload each -- the ordering is applied
#: locally because ``/browse.json`` is a statically generated page that
#: ignores query parameters (verified from the VPS: ``?page=2`` and
#: ``?search=`` return the identical 166 entries).
BROWSE_MODES: tuple[BrowseMode, ...] = (
    BrowseMode(id="default", label="Latest Updates"),
    BrowseMode(id="popular", label="Popular"),
    BrowseMode(id="new", label="Recently Added"),
    BrowseMode(id="alphabetical", label="A-Z"),
)

_LATEST_MODES = frozenset({"default", "latest", "updates"})


def uses_latest_feed(sort: str | None) -> bool:
    """Which of the two catalog payloads a sort mode needs.

    ``/latest.json`` carries each series' three newest chapters (so the card
    can show "Chapter 14"); ``/browse.json`` carries full metadata and
    ``popularityRank``. Each mode reads exactly one of them.
    """
    return (sort or "default").strip().lower() in _LATEST_MODES


def parse_catalog(payload: dict[str, Any]) -> list[Series]:
    """Parse ``/browse.json`` into the full comic catalog, title-ordered."""
    props = payload.get("pageProps") if isinstance(payload, dict) else None
    entries = props.get("series") if isinstance(props, dict) else None
    if not isinstance(entries, list):
        return []
    catalog: list[Series] = []
    for entry in entries:
        if not _is_comic(entry):
            continue
        title = _text(entry.get("title"))
        if not title:
            continue
        key = _series_key_of(entry)
        catalog.append(
            Series(
                id=key,
                title=title,
                canonical_path=series_url(key),
                description=_clean_description(entry.get("description")),
                cover_url=cover_url(key, entry.get("cover"), entry.get("last_edit")),
                author=_join_people(entry.get("author")),
                artist=_join_people(entry.get("artist")),
                status=_text(entry.get("status")) or None,
                genres=_genres(entry),
            )
        )
    return catalog


def catalog_sort_key(sort: str | None) -> Any:
    """Ordering applied to the parsed catalog for a non-latest browse mode."""
    mode = (sort or "default").strip().lower()
    if mode == "popular":
        return "popular"
    if mode == "new":
        return "new"
    return "alphabetical"


def order_catalog(
    catalog: list[Series],
    ranks: dict[str, int],
    added: dict[str, int],
    sort: str | None,
) -> list[Series]:
    mode = catalog_sort_key(sort)
    if mode == "popular":
        # popularityRank is 1-based and dense; unranked entries sort last.
        return sorted(catalog, key=lambda s: (ranks.get(s.id, 10**9), s.title.lower()))
    if mode == "new":
        return sorted(catalog, key=lambda s: (-added.get(s.id, 0), s.title.lower()))
    return sorted(catalog, key=lambda s: s.title.lower())


def parse_catalog_rankings(payload: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    """``(popularityRank, added-at)`` per series key, for local ordering."""
    props = payload.get("pageProps") if isinstance(payload, dict) else None
    entries = props.get("series") if isinstance(props, dict) else None
    ranks: dict[str, int] = {}
    added: dict[str, int] = {}
    if not isinstance(entries, list):
        return ranks, added
    for entry in entries:
        if not _is_comic(entry):
            continue
        key = _series_key_of(entry)
        rank = entry.get("popularityRank")
        if isinstance(rank, int):
            ranks[key] = rank
        stamp = entry.get("time")
        if isinstance(stamp, (int, float)):
            added[key] = int(stamp)
    return ranks, added


def parse_latest_feed(payload: dict[str, Any]) -> list[Series]:
    """Parse ``/latest.json`` into recency-ordered series.

    The feed is *approximately* newest-first upstream but not strictly so
    (verified from the VPS), hence the explicit re-sort on each series' newest
    chapter release date -- a listing whose order wobbles between refreshes
    reads as a bug.
    """
    props = payload.get("pageProps") if isinstance(payload, dict) else None
    entries = props.get("allSeries") if isinstance(props, dict) else None
    if not isinstance(entries, list):
        return []

    ordered: list[tuple[int, int, Series]] = []
    for position, entry in enumerate(entries):
        if not _is_comic(entry):
            continue
        title = _text(entry.get("title"))
        if not title:
            continue
        key = _series_key_of(entry)
        chapters = entry.get("chapters")
        chapters = chapters if isinstance(chapters, list) else []
        newest = 0
        latest_label: str | None = None
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            released = chapter.get("release_date")
            released = int(released) if isinstance(released, (int, float)) else 0
            if released >= newest:
                newest = released
                number = parse_chapter_number(chapter.get("chapter"))
                latest_label = _chapter_display_title(chapter, number)
        ordered.append(
            (
                newest,
                -position,
                Series(
                    id=key,
                    title=title,
                    canonical_path=series_url(key),
                    cover_url=cover_url(key, entry.get("cover"), entry.get("last_edit")),
                    status=_text(entry.get("status")) or None,
                    latest_chapter=latest_label,
                ),
            )
        )
    ordered.sort(key=lambda row: (-row[0], -row[1]))
    return [row[2] for row in ordered]


def paginate(items: list[Series], page: int, page_size: int = PAGE_SIZE) -> PaginatedSeriesList:
    if page < 1:
        page = 1
    start = (page - 1) * page_size
    return PaginatedSeriesList(
        items=items[start : start + page_size],
        page=page,
        page_size=page_size,
        total=len(items),
    )


def matches_query(series: Series, query: str) -> bool:
    """Whole-catalog local search.

    ``/browse.json`` is statically generated and ignores ``?search=`` (VPS
    check: it returned all 166 entries either way), and the site's own search
    box filters the same client-side array. Matching here means search costs
    ZERO network requests once the catalog is cached.
    """
    needle = query.strip().lower()
    if not needle:
        return True
    terms = [term for term in needle.split() if term]
    haystack = " ".join(
        part.lower()
        for part in (
            series.title,
            series.author or "",
            series.artist or "",
            " ".join(series.genres),
        )
        if part
    )
    return all(term in haystack for term in terms)


def search_rank(series: Series, query: str) -> tuple[int, int, str]:
    """Rank exact/prefix title hits above incidental author or genre hits."""
    needle = query.strip().lower()
    title = series.title.lower()
    if title == needle:
        bucket = 0
    elif title.startswith(needle):
        bucket = 1
    elif needle in title:
        bucket = 2
    else:
        bucket = 3
    return (bucket, len(series.title), title)


def collect_genres(catalog: list[Series]) -> list[BrowseMode]:
    names = sorted({genre for series in catalog for genre in series.genres})
    return [BrowseMode(id=name, label=name) for name in names]


# --------------------------------------------------------------------------
# series detail + chapters (ONE payload)
# --------------------------------------------------------------------------


def parse_series_detail(payload: dict[str, Any], series_key: str) -> Series | None:
    props = payload.get("pageProps") if isinstance(payload, dict) else None
    entry = props.get("series") if isinstance(props, dict) else None
    if not isinstance(entry, dict):
        return None
    title = _text(entry.get("title"))
    if not title:
        return None
    key = _series_key_of(entry) if _is_comic(entry) else series_key
    chapters = parse_chapters(payload, key)
    latest = chapters[-1].title if chapters else None
    return Series(
        id=key,
        title=title,
        chapter_count=len(chapters),
        canonical_path=series_url(key),
        description=_clean_description(entry.get("description")),
        cover_url=cover_url(
            key, entry.get("cover"), entry.get("last_edit") or entry.get("time")
        ),
        author=_join_people(entry.get("author")),
        artist=_join_people(entry.get("artist")),
        status=_text(entry.get("status")) or None,
        genres=_genres(entry),
        latest_chapter=latest,
    )


def parse_chapters(payload: dict[str, Any], series_key: str) -> list[Chapter]:
    """Parse the chapter list that ships inside the series payload.

    Returned oldest-first (the site serves newest-first) because the rest of
    the app treats ``chapters[-1]`` as the newest.
    """
    props = payload.get("pageProps") if isinstance(payload, dict) else None
    entries = props.get("chapters") if isinstance(props, dict) else None
    if not isinstance(entries, list):
        return []

    rows: list[tuple[float, int, Chapter]] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        token = _text(entry.get("token"))
        if not token:
            continue
        number = parse_chapter_number(entry.get("chapter"))
        chapter_key = make_chapter_key(series_key, token)
        rows.append(
            (
                number if number is not None else -1.0,
                position,
                Chapter(
                    id=chapter_key,
                    series_id=series_key,
                    title=_chapter_display_title(entry, number),
                    number=number,
                    page_count=0,
                    release_date=_release_date(entry.get("release_date")),
                ),
            )
        )
    # Ascending by the site's own numbering; ties keep the upstream order
    # reversed so a newest-first source still ends oldest-first.
    rows.sort(key=lambda row: (row[0], -row[1]))
    return [row[2] for row in rows]


# --------------------------------------------------------------------------
# chapter pages (ONE payload, zero requests per page)
# --------------------------------------------------------------------------


def parse_chapter_pages(payload: dict[str, Any], chapter_key: str) -> list[Page]:
    """Build every page URL from the chapter's image manifest.

    ``images`` is a JSON object keyed by stringified index (``"0"``, ``"1"``,
    ...), each value carrying ``name``/``width``/``height``. Ordering by the
    numeric key matters: JSON object order is not guaranteed, and ``"10"``
    sorts before ``"2"`` as a string.

    Entries flagged ``decoy`` or missing a ``name`` are skipped -- the site's
    own reader bundle filters exactly those (``e && !0 !== e.decoy &&
    "string" == typeof e?.name && e.name.length > 0``). No decoys were present
    in any chapter sampled from the VPS, so this is a guard against the site
    turning the feature on, not a workaround for current behaviour.
    """
    split = split_chapter_key(chapter_key)
    if split is None:
        return []
    series_key, token = split

    props = payload.get("pageProps") if isinstance(payload, dict) else None
    chapter = props.get("chapter") if isinstance(props, dict) else None
    if not isinstance(chapter, dict):
        return []
    images = chapter.get("images")
    if not isinstance(images, dict):
        return []
    version = chapter.get("edit_time") or chapter.get("release_date")

    def _index(key: str) -> tuple[int, int, str]:
        text = str(key)
        return (0, int(text), "") if text.lstrip("-").isdigit() else (1, 0, text)

    pages: list[Page] = []
    for raw_key in sorted(images.keys(), key=_index):
        entry = images[raw_key]
        if not isinstance(entry, dict):
            continue
        if entry.get("decoy"):
            continue
        name = _text(entry.get("name"))
        if not name:
            continue
        number = len(pages) + 1
        width = entry.get("width")
        height = entry.get("height")
        pages.append(
            Page(
                id=make_page_id(chapter_key, number),
                chapter_id=chapter_key,
                number=number,
                remote_url=page_image_url(series_key, token, name, version),
                width=int(width) if isinstance(width, (int, float)) and width > 0 else None,
                height=int(height) if isinstance(height, (int, float)) and height > 0 else None,
            )
        )
    return pages
