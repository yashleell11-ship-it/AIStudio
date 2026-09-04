"""Mapping helpers for MangaBuddy (comizy.io) JSON API payloads.

mangabuddy.com now 301s to comizy.io, a Next.js Pages Router front end backed
by a public, unauthenticated JSON API at ``api.comizy.io``. Every stage this
connector needs is one API call returning structured JSON, so there is no HTML
parsing here at all.

Identity
--------
The API is keyed by the site's own short hash ids ("hsid"), never by slug --
``GET /titles/martial-peak`` answers 400 ("Title ID must contain only
alphanumeric characters"). Slugs are also explicitly mutable upstream (titles
carry a ``redirect_slug`` field), so the hsid is both the only workable key and
the more stable one.

* ``series_key``  = the title hsid, e.g. ``"A5LeWJj1"``.
* ``chapter_key`` = ``"<title hsid>/<chapter hsid>"``, e.g.
  ``"A5LeWJj1/MjPw7z45"`` -- the chapter images route needs *both* ids and
  ``get_chapter_pages`` only receives the one key, so the key carries both.
  The composite is a format this module owns (``make_chapter_key`` /
  ``split_chapter_key``); the site's ids inside it stay opaque and are never
  interpreted.
* ``page_id``     = ``"<chapter_key>:<n>"``.
"""

from __future__ import annotations

import re
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

#: Public site. Used for canonical paths and as the image/API ``Referer``.
SITE_BASE = "https://comizy.io"
#: JSON API host. Every request this connector makes goes here.
API_BASE = "https://api.comizy.io"

SEARCH_PATH = "/titles/search"

#: The site's own grid page size. The API defaults to 20; 24 matches the site.
PAGE_SIZE = 24

DEFAULT_SORT = "latest"

#: Browse modes -> the site's own sort ids. All eight are in the set the API
#: names in its own 400 ("Sort field must be one of: newest, rating, views,
#: popular, bookmarks, chapters, comments, latest, added_date, views_today,
#: views_7days, views_30days").
#:
#: ``alphabetical`` and ``best_match`` are deliberately absent -- neither is a
#: real API sort. The site's own UI offers both, but ``best_match`` is how it
#: spells "send no sort at all" (see ``search_params``) and ``alphabetical``
#: answers 400; its front end swallows that into an empty grid.
BROWSE_MODES: tuple[tuple[str, str], ...] = (
    ("default", "Latest Updates"),
    ("popular", "Most Followed"),
    ("newest", "Recently Added"),
    ("views_today", "Trending Today"),
    ("views_7days", "Trending This Week"),
    ("views", "Most Viewed"),
    ("rating", "Highest Rated"),
    ("chapters", "Most Chapters"),
)

_VALID_SORTS = frozenset(mode_id for mode_id, _ in BROWSE_MODES if mode_id != "default")

#: Genre slugs the site exposes, captured from its own genre payload.
GENRES: tuple[tuple[str, str], ...] = (
    ("action", "Action"),
    ("adaptation", "Adaptation"),
    ("adult", "Adult"),
    ("adventure", "Adventure"),
    ("anthology", "Anthology"),
    ("comedy", "Comedy"),
    ("comic", "Comic"),
    ("cooking", "Cooking"),
    ("demons", "Demons"),
    ("doujinshi", "Doujinshi"),
    ("drama", "Drama"),
    ("ecchi", "Ecchi"),
    ("fantasy", "Fantasy"),
    ("full-color", "Full Color"),
    ("game", "Game"),
    ("gender-bender", "Gender bender"),
    ("ghosts", "Ghosts"),
    ("harem", "Harem"),
    ("hentai", "Hentai"),
    ("historical", "Historical"),
    ("horror", "Horror"),
    ("isekai", "Isekai"),
    ("josei", "Josei"),
    ("long-strip", "Long strip"),
    ("magic", "Magic"),
    ("manga", "Manga"),
    ("manhua", "Manhua"),
    ("manhwa", "Manhwa"),
    ("martial-arts", "Martial arts"),
    ("mature", "Mature"),
    ("mecha", "Mecha"),
    ("medical", "Medical"),
    ("military", "Military"),
    ("monster", "Monster"),
    ("monster-girls", "Monster girls"),
    ("monsters", "Monsters"),
    ("music", "Music"),
    ("mystery", "Mystery"),
    ("office-workers", "Office workers"),
    ("one-shot", "One shot"),
    ("police", "Police"),
    ("psychological", "Psychological"),
    ("reincarnation", "Reincarnation"),
    ("romance", "Romance"),
    ("school-life", "School life"),
    ("sci-fi", "Sci fi"),
    ("science-fiction", "Science fiction"),
    ("shoujo", "Shoujo"),
    ("shoujo-ai", "Shoujo ai"),
    ("shounen", "Shounen"),
    ("shounen-ai", "Shounen ai"),
    ("slice-of-life", "Slice of life"),
    ("smut", "Smut"),
    ("soft-yaoi", "Soft Yaoi"),
    ("sports", "Sports"),
    ("super-power", "Super Power"),
    ("superhero", "Superhero"),
    ("supernatural", "Supernatural"),
    ("thriller", "Thriller"),
    ("time-travel", "Time travel"),
    ("tragedy", "Tragedy"),
    ("vampire", "Vampire"),
    ("vampires", "Vampires"),
    ("video-games", "Video games"),
    ("villainess", "Villainess"),
    ("web-comic", "Web comic"),
    ("webtoons", "Webtoons"),
    ("worth-the-read", "Worth the read"),
    ("yaoi", "Yaoi"),
    ("yuri", "Yuri"),
    ("zombies", "Zombies"),
)

_GENRE_SLUGS = frozenset(slug for slug, _ in GENRES)

#: An hsid is a short alphanumeric hash. Anything else is not an API id, and
#: the API rejects it with a 400 rather than a 404, so screen it here.
_HSID_RE = re.compile(r"^[A-Za-z0-9]{4,32}$")

_CHAPTER_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def list_browse_modes() -> list[BrowseMode]:
    return [BrowseMode(id=mode_id, label=label) for mode_id, label in BROWSE_MODES]


def list_genres() -> list[BrowseMode]:
    return [BrowseMode(id=slug, label=label) for slug, label in GENRES]


def explicit_sort(sort: str | None) -> str | None:
    """The caller's chosen sort, or None when they did not choose one."""
    cleaned = (sort or "").strip()
    if not cleaned or cleaned == "default":
        return None
    return cleaned if cleaned in _VALID_SORTS else None


def normalize_sort(sort: str | None) -> str:
    """Map a browse-mode id onto the site's own sort id (for browse/logging)."""
    return explicit_sort(sort) or DEFAULT_SORT


def normalize_genre(genre: str | None) -> str | None:
    cleaned = (genre or "").strip().lower()
    return cleaned if cleaned in _GENRE_SLUGS else None


def is_api_id(value: str) -> bool:
    return bool(_HSID_RE.match(value))


def normalize_series_key(value: str) -> str:
    """Reduce any accepted reference down to the bare title hsid.

    Accepts the key itself, or a ``<title hsid>/<chapter hsid>`` chapter key,
    so a caller holding either can ask for the series.
    """
    cleaned = (value or "").strip().strip("/")
    return cleaned.split("/", 1)[0]


def make_chapter_key(series_key: str, chapter_id: str) -> str:
    return f"{series_key.strip().strip('/')}/{chapter_id.strip().strip('/')}"


def split_chapter_key(chapter_key: str) -> tuple[str, str] | None:
    """Split a composite chapter key back into (title hsid, chapter hsid)."""
    cleaned = (chapter_key or "").strip().strip("/")
    series_key, sep, chapter_id = cleaned.partition("/")
    if not sep or not series_key or not chapter_id:
        return None
    return series_key, chapter_id


def make_page_id(chapter_key: str, page_number: int) -> str:
    return f"{chapter_key}:{page_number}"


def page_id_chapter_key(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_key, _, _number = page_id.rpartition(":")
    return chapter_key or None


def series_path(series_key: str) -> str:
    return f"/titles/{series_key}"


def chapters_path(series_key: str) -> str:
    return f"/titles/{series_key}/chapters"


def chapter_detail_path(series_key: str, chapter_id: str) -> str:
    """The chapter route that carries the COMPLETE image list.

    Deliberately not ``.../images``: verified from the VPS across three
    different chapters, that route returns exactly 3 image URLs regardless of
    the chapter's real length (85, 13 and 12 respectively) and ignores
    ``limit``/``page``/``all`` -- it is a teaser, and building on it would ship
    a reader that silently drops every page past the third. This route returns
    every image plus per-page ``width``/``height``.
    """
    return f"/titles/{series_key}/chapters/{chapter_id}"


def search_params(
    query: str,
    *,
    page: int,
    sort: str | None = None,
    genre: str | None = None,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": max(1, page), "limit": page_size}
    cleaned_query = (query or "").strip()
    chosen = explicit_sort(sort)
    if cleaned_query:
        params["q"] = cleaned_query
        # Relevance ranking is what you get by sending NO sort at all. The
        # site's "Best Match" option is exactly that -- ``sort=best_match``
        # answers 400. Sending the browse default here instead would rank a
        # title search by last-updated, which buries the obvious hit: verified
        # live, "solo leveling" returns "Leveling Up With Skills" first under
        # sort=latest and "Solo Leveling" first with the sort omitted.
        if chosen is not None:
            params["sort"] = chosen
    else:
        params["sort"] = chosen or DEFAULT_SORT
    normalized_genre = normalize_genre(genre)
    if normalized_genre:
        params["genres"] = normalized_genre
    return params


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _names(entries: Any) -> tuple[str, ...]:
    """Pull the ``name`` off a list of {name, slug} records."""
    if not isinstance(entries, list):
        return ()
    out: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = _clean_text(entry.get("name"))
            if name:
                out.append(name)
    return tuple(out)


def _joined(entries: Any) -> str | None:
    names = _names(entries)
    return ", ".join(names) if names else None


def _status(value: Any) -> str | None:
    text = _clean_text(value)
    return text.title() if text else None


def parse_chapter_number(name: Any, slug: Any) -> float | None:
    """The chapter's own number, from the site's own labelling.

    Never the API's ``number`` field: that is a 1-based ordinal over the
    series, not the chapter number. On ``stay-alive`` its ``chapter-0`` is
    ``number: 1`` and ``chapter-60`` is ``number: 61`` -- using it would shift
    every chapter in every series by one.
    """
    for candidate in (name, slug):
        text = _clean_text(candidate)
        if not text:
            continue
        match = _CHAPTER_NUMBER_RE.search(text)
        if match is None:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        return value
    return None


def series_from_item(item: Any) -> Series | None:
    """Map one search/browse result record onto a Series."""
    if not isinstance(item, dict):
        return None
    series_key = _clean_text(item.get("id"))
    title = _clean_text(item.get("name"))
    if not series_key or not title:
        return None

    stats = item.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    chapter_count = stats.get("chapters_count")
    latest = item.get("latest_chapters")
    latest_title = None
    if isinstance(latest, list) and latest and isinstance(latest[0], dict):
        latest_title = _clean_text(latest[0].get("name")) or None

    canonical = _clean_text(item.get("url")) or None
    cover = _clean_text(item.get("cover")) or None

    return Series(
        id=series_key,
        title=title,
        chapter_count=int(chapter_count) if isinstance(chapter_count, int) else 0,
        canonical_path=canonical,
        description=_clean_text(item.get("summary")) or None,
        cover_url=cover,
        author=_joined(item.get("authors")),
        artist=_joined(item.get("artists")),
        status=_status(item.get("status")),
        genres=_names(item.get("genres")),
        latest_chapter=latest_title,
    )


def parse_series_list(
    payload: Any,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    """Map a ``/titles/search`` envelope onto a paginated listing."""
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    raw_items = data.get("items")
    items: list[Series] = []
    if isinstance(raw_items, list):
        for entry in raw_items:
            series = series_from_item(entry)
            if series is not None:
                items.append(series)

    pagination = data.get("pagination")
    pagination = pagination if isinstance(pagination, dict) else {}
    total = pagination.get("total")
    has_next = pagination.get("has_next")
    reported_page = pagination.get("page")
    reported_limit = pagination.get("limit")

    return PaginatedSeriesList(
        items=items,
        page=int(reported_page) if isinstance(reported_page, int) else page,
        page_size=int(reported_limit) if isinstance(reported_limit, int) else page_size,
        total=int(total) if isinstance(total, int) else len(items),
        # ``total`` saturates at 10000 with ``total_relation: "gte"``, so the
        # API's own has_next is the only trustworthy end-of-list signal.
        api_has_more=bool(has_next) if isinstance(has_next, bool) else None,
    )


def parse_series_detail(payload: Any, series_key: str) -> Series | None:
    """Map a ``/titles/<hsid>`` envelope onto a Series."""
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    title_record = data.get("title")
    if not isinstance(title_record, dict):
        return None
    series = series_from_item(title_record)
    if series is None:
        return None
    # The API echoes its own id; trust the key the caller asked with so the
    # object round-trips against whatever the library stored.
    if series.id != series_key:
        series = Series(
            id=series_key,
            title=series.title,
            chapter_count=series.chapter_count,
            canonical_path=series.canonical_path,
            description=series.description,
            cover_url=series.cover_url,
            author=series.author,
            artist=series.artist,
            status=series.status,
            genres=series.genres,
            latest_chapter=series.latest_chapter,
        )
    return series


def declared_chapter_count(payload: Any) -> int:
    """``stats.chapters_count`` off a title detail envelope."""
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    title_record = data.get("title")
    if not isinstance(title_record, dict):
        return 0
    stats = title_record.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    count = stats.get("chapters_count")
    return int(count) if isinstance(count, int) else 0


def _chapters_from_records(records: Any, series_key: str) -> list[Chapter]:
    if not isinstance(records, list):
        return []
    chapters: list[Chapter] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        chapter_id = _clean_text(record.get("id"))
        if not chapter_id:
            continue
        name = _clean_text(record.get("name"))
        slug = _clean_text(record.get("slug"))
        chapters.append(
            Chapter(
                id=make_chapter_key(series_key, chapter_id),
                series_id=series_key,
                title=name or slug or chapter_id,
                number=parse_chapter_number(name, slug),
                # Page counts cost a request per chapter; the connector fills
                # them in from its page cache once a chapter has been opened.
                page_count=0,
                release_date=_clean_text(record.get("updated_at")) or None,
            )
        )
    # Upstream lists newest-first; the reader wants oldest-first.
    chapters.reverse()
    return chapters


def parse_chapters(payload: Any, series_key: str) -> list[Chapter]:
    """Map a ``/titles/<hsid>/chapters`` envelope onto the chapter list."""
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    return _chapters_from_records(data.get("chapters"), series_key)


def parse_embedded_chapters(payload: Any, series_key: str) -> list[Chapter]:
    """Chapters carried inline on a title detail envelope.

    The detail route embeds only the newest 50 (verified: ``martial-peak``
    reports 3880 chapters and embeds 50). The connector uses this list only
    when it is already complete, and otherwise spends one request on the
    dedicated chapter-list route.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    title_record = data.get("title")
    if not isinstance(title_record, dict):
        return []
    return _chapters_from_records(title_record.get("chapters"), series_key)


def parse_chapter_pages(payload: Any, chapter_key: str) -> list[Page]:
    """Map a chapter detail envelope onto its pages.

    Prefers ``chapter.pages`` (url + width + height, so the reader can reserve
    layout before the bytes arrive) and falls back to the plain
    ``chapter.images`` URL list.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    chapter_record = data.get("chapter")
    if not isinstance(chapter_record, dict):
        return []

    pages: list[Page] = []
    raw_pages = chapter_record.get("pages")
    if isinstance(raw_pages, list) and raw_pages:
        for entry in raw_pages:
            if not isinstance(entry, dict):
                continue
            url = _clean_text(entry.get("url"))
            if not url:
                continue
            width = entry.get("width")
            height = entry.get("height")
            number = len(pages) + 1
            pages.append(
                Page(
                    id=make_page_id(chapter_key, number),
                    chapter_id=chapter_key,
                    number=number,
                    remote_url=url,
                    width=int(width) if isinstance(width, int) and width > 0 else None,
                    height=int(height) if isinstance(height, int) and height > 0 else None,
                )
            )
        if pages:
            return pages

    raw_images = chapter_record.get("images")
    if isinstance(raw_images, list):
        for entry in raw_images:
            url = _clean_text(entry)
            if not url:
                continue
            number = len(pages) + 1
            pages.append(
                Page(
                    id=make_page_id(chapter_key, number),
                    chapter_id=chapter_key,
                    number=number,
                    remote_url=url,
                )
            )
    return pages
