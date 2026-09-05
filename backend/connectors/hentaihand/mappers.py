"""Map HentaiHand's public JSON API onto normalized connector models.

Endpoint map (verified from the VPS 2026-09-05, inside
``manhwamaniacs-backend`` so through production's exact egress):

* ``/api/comics?page=N&sort=<mode>``   -- Laravel paginator, 18 comics/page,
  ``total`` 655,080 over 36,394 pages. ``sort`` is the only knob that moves
  the ordering; ``order``/``recent``/``newest`` are silently ignored and fall
  back to id-ascending, which is *oldest* first -- see ``BROWSE_MODES``.
* ``/api/comics?page=N&q=<terms>``     -- search, identical envelope.
* ``/api/comics?page=N&tags[]=<id>``   -- tag browse. The filter takes tag
  *ids*, not slugs: ``tags[]=big-breasts`` answers ``total: 0``, so the
  genre table below carries the numeric ids.
* ``/api/comics/<slug>``               -- detail. Addressed by SLUG, not id:
  ``/api/comics/1`` resolves comic 1356, whose slug happens to be ``"1"``.
* ``/api/comics/<slug>/images``        -- every page URL in one response,
  ``{comic, chapter, next_chapter, images:[{id, page, source_url, ...}]}``.

Identity keys are the API's own slugs -- opaque strings, stored and passed
raw (house law). They are lowercase alphanumerics and dashes, so the colon
that separates a page id's index never occurs inside one.
"""

from __future__ import annotations

from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://hentaihand.com"

#: The API's fixed page size. It ignores ``per_page`` -- every listing
#: response measured came back with ``per_page: 18``.
PAGE_SIZE = 18

COMICS_PATH = "/api/comics"

#: Covers, thumbnails and page images all live on ``cdn.hentaihand.com``;
#: the suffix covers the apex too, which serves the site's own assets.
IMAGE_HOST_SUFFIX = "hentaihand.com"

#: Separates the gallery slug from the 1-based page index in a page id.
PAGE_ID_SEPARATOR = ":"


# --- browse modes -----------------------------------------------------------

#: Mode id -> (label, ``sort`` value). The default is ``uploaded_at`` and not
#: the API's own default on purpose: with no ``sort`` the paginator orders by
#: id ascending, i.e. it opens on 2016 uploads, which reads as a dead source.
BROWSE_MODES: dict[str, tuple[str, str]] = {
    "default": ("Latest", "uploaded_at"),
    "popularity": ("Trending", "popularity"),
    "favorites": ("Most Favorited", "favorites"),
    "pages": ("Longest", "pages"),
    "title": ("By Title", "title"),
}

DEFAULT_MODE = "default"

#: Tag slug -> (label, tag id), read from ``/api/tags`` on 2026-09-05. Ids are
#: hard-coded because the tag endpoint pages five at a time over 8,169 tags --
#: resolving a slug at request time would cost an unbounded scan.
#:
#: This is a browse *menu*, not a content filter: it deliberately leaves out
#: the catalogue's most extreme tag categories rather than offering them as
#: one-click tiles. Nothing here narrows what search or the listings return.
GENRES: dict[str, tuple[str, int]] = {
    "big-breasts": ("Big Breasts", 29),
    "nakadashi": ("Nakadashi", 26),
    "anal": ("Anal", 30),
    "group": ("Group", 6),
    "blowjob": ("Blowjob", 27),
    "stockings": ("Stockings", 7),
    "schoolgirl-uniform": ("Schoolgirl Uniform", 46),
    "full-color": ("Full Color", 32),
    "males-only": ("Males Only", 37),
    "yaoi": ("Yaoi", 35),
    "futanari": ("Futanari", 33),
    "netorare": ("Netorare", 110),
    "uncensored": ("Uncensored", 44),
    "swimsuit": ("Swimsuit", 19),
    "bikini": ("Bikini", 20),
    "kemonomimi": ("Kemonomimi", 21),
    "catgirl": ("Catgirl", 22),
    "muscle": ("Muscle", 13),
    "ponytail": ("Ponytail", 36),
    "kissing": ("Kissing", 42),
    "pantyhose": ("Pantyhose", 47),
    "teacher": ("Teacher", 49),
    "story-arc": ("Story Arc", 48),
    "x-ray": ("X-Ray", 10),
}


def list_browse_modes() -> list[BrowseMode]:
    return [BrowseMode(id=key, label=label) for key, (label, _sort) in BROWSE_MODES.items()]


def list_genres() -> list[BrowseMode]:
    return [BrowseMode(id=slug, label=label) for slug, (label, _id) in GENRES.items()]


def normalize_sort(sort: str | None) -> str:
    if not sort:
        return DEFAULT_MODE
    return sort if sort in BROWSE_MODES else DEFAULT_MODE


def browse_params(sort: str | None, page: int) -> dict[str, Any]:
    _label, sort_value = BROWSE_MODES[normalize_sort(sort)]
    return {"page": max(page, 1), "sort": sort_value}


def search_params(query: str, page: int, *, sort: str | None = None) -> dict[str, Any]:
    params = browse_params(sort, page)
    params["q"] = query.strip()
    return params


def genre_params(genre: str, page: int, *, sort: str | None = None) -> dict[str, Any] | None:
    """Query for one tag, or ``None`` when the tag is not in the menu.

    The API filters on tag ids only, so an unknown slug cannot be turned into
    a request at all -- returning None lets the connector answer with an empty
    page instead of silently serving the unfiltered catalog.
    """
    entry = GENRES.get(genre.strip())
    if entry is None:
        return None
    params = browse_params(sort, page)
    params["tags[]"] = entry[1]
    return params


# --- identity ---------------------------------------------------------------


def _strip_site(value: str) -> str:
    text = (value or "").strip()
    for prefix in (f"{SITE_BASE}/", "https://hentaihand.com/", "http://hentaihand.com/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip("/")


def normalize_series_key(value: str) -> str:
    """The API slug, from any of the shapes the app may hand back."""
    text = _strip_site(value)
    for prefix in ("api/comics/", "comic/", "g/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip("/")


def series_path(series_key: str) -> str:
    return f"{COMICS_PATH}/{normalize_series_key(series_key)}"


def images_path(series_key: str) -> str:
    return f"{COMICS_PATH}/{normalize_series_key(series_key)}/images"


def canonical_path(series_key: str) -> str:
    return f"/comic/{normalize_series_key(series_key)}"


def make_page_id(series_key: str, number: int) -> str:
    return f"{series_key}{PAGE_ID_SEPARATOR}{number}"


def page_id_series_key(page_id: str) -> str | None:
    series_key, sep, _index = (page_id or "").rpartition(PAGE_ID_SEPARATOR)
    if not sep or not series_key:
        return None
    return series_key


# --- parsing ----------------------------------------------------------------


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _names(entries: Any) -> tuple[str, ...]:
    if not isinstance(entries, list):
        return ()
    return tuple(
        name for name in (_text(entry.get("name")) for entry in entries if isinstance(entry, dict)) if name
    )


#: Every comic is one gallery: ``chapters_count`` was 0 and ``next_chapter``
#: null on every comic sampled across five listing pages, so the connector
#: publishes exactly one chapter per series rather than inventing a list.
CHAPTER_TITLE = "Gallery"


def comic_to_series(item: dict[str, Any]) -> Series | None:
    """One paginator entry (or a detail body) as a Series.

    Detail and listing entries share this shape; detail adds ``artists`` /
    ``authors`` / ``groups``, which the listing omits, so both flow through
    one mapper and the extra fields simply stay empty on a listing card.
    """
    slug = _text(item.get("slug"))
    title = _text(item.get("title"))
    if not slug or not title:
        return None

    category = item.get("category") if isinstance(item.get("category"), dict) else {}
    language = item.get("language") if isinstance(item.get("language"), dict) else {}
    genres = _names(item.get("tags"))
    # The catalogue is untitled doujinshi with no "status" of its own, so the
    # only honest status line is the language + category the API does publish.
    facets = [name for name in (_text(category.get("name")), _text(language.get("name"))) if name]

    artists = _names(item.get("artists")) or _names(item.get("groups"))
    authors = _names(item.get("authors"))

    return Series(
        id=slug,
        title=title,
        canonical_path=canonical_path(slug),
        description=_text(item.get("description")) or _text(item.get("alternative_title")),
        cover_url=_text(item.get("thumb_url")) or _text(item.get("image_url")),
        author=", ".join(authors) if authors else None,
        artist=", ".join(artists) if artists else None,
        status=" / ".join(facets) if facets else None,
        genres=genres,
        chapter_count=1,
        latest_chapter=CHAPTER_TITLE,
    )


def comic_to_chapter(item: dict[str, Any]) -> Chapter | None:
    slug = _text(item.get("slug"))
    if not slug:
        return None
    try:
        page_count = int(item.get("pages") or 0)
    except (TypeError, ValueError):
        page_count = 0
    return Chapter(
        id=slug,
        series_id=slug,
        title=CHAPTER_TITLE,
        number=1.0,
        page_count=max(page_count, 0),
        release_date=_text(item.get("uploaded_at")),
    )


def parse_series_list(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    """A Laravel paginator envelope as a normalized listing.

    ``total`` and ``last_page`` are authoritative here, so ``has_more`` is an
    exact answer rather than the "did a card come back?" guess an HTML source
    forces.
    """
    entries = payload.get("data")
    items: list[Series] = []
    seen: set[str] = set()
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            series = comic_to_series(entry)
            if series is None or series.id in seen:
                continue
            seen.add(series.id)
            items.append(series)

    current = _int(payload.get("current_page"), default=max(page, 1))
    per_page = _int(payload.get("per_page"), default=PAGE_SIZE) or PAGE_SIZE
    total = _int(payload.get("total"), default=len(items))
    last_page = _int(payload.get("last_page"), default=0)
    return PaginatedSeriesList(
        items=items,
        page=current,
        page_size=per_page,
        total=total,
        api_has_more=bool(payload.get("next_page_url")) or current < last_page,
    )


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_images(payload: dict[str, Any], series_key: str) -> list[Page]:
    """Page images, ordered by the API's own ``page`` field.

    The endpoint returns them in order already, but ``page`` is what the
    reader numbers against, so sorting on it keeps a reordered response from
    silently shuffling a chapter.
    """
    entries = payload.get("images")
    if not isinstance(entries, list):
        return []

    ordered: list[tuple[int, str]] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        url = _text(entry.get("source_url"))
        if not url:
            continue
        ordered.append((_int(entry.get("page"), default=index), url))
    ordered.sort(key=lambda item: item[0])

    pages: list[Page] = []
    seen: set[str] = set()
    for _number, url in ordered:
        if url in seen:
            continue
        seen.add(url)
        index = len(pages) + 1
        pages.append(
            Page(
                id=make_page_id(series_key, index),
                chapter_id=series_key,
                number=index,
                remote_url=url,
            )
        )
    return pages
