"""Map Manhwa18.net's Inertia pages onto normalized connector models.

The site is Laravel + Inertia.js, which means every page ships its ENTIRE
server-side payload inside one attribute:

    <div id="app" data-page="{&quot;component&quot;:...,&quot;props&quot;:{...}}">

so nothing here executes JavaScript or scrapes markup -- the parsers below
HTML-unescape that attribute and read JSON. The rendered DOM is ignored.

Endpoint map (verified from the VPS 2026-09-05, inside
``manhwamaniacs-backend`` so through production's exact egress):

* ``/manga-list?page=N[&sort=new|top]`` -- component ``MangaList``, props
  ``paginate``: a Laravel paginator, 24 series/page, ``total`` 2,277.
  Unknown ``sort`` values fall through to the default (latest updated).
* ``/tim-kiem?q=<terms>&page=N``        -- component ``Search``, props
  ``mangas`` (same paginator shape under a different key). The route name is
  Vietnamese and is NOT ``/search``, which 404s; it comes from the site's own
  ``SearchAction`` schema block.
* ``/genre/<slug>?page=N``              -- component ``MangaList``, props
  ``paginate`` + ``genre``.
* ``/manga/<slug>``                     -- component ``Manga``, props
  ``manga`` + ``chapters`` (the FULL chapter list), so detail and chapter
  list cost exactly one request.
* ``/manga/<slug>/<chapter-slug>``      -- component ``Chapter``, props
  ``chapterImages`` (``[{src, source_width, source_height, variants}]``),
  so a chapter costs one request and a page image costs zero extra.

Identity keys are the site's own slugs. A chapter key joins both slugs with a
slash (``the-seed-of-destiny/chapter-49``) because a chapter slug is only
unique within its series -- the app stores it raw (house law).
"""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import replace
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://manhwa18.net"

#: Laravel's page size on every listing route measured (browse, genre: 24;
#: search: 18). The envelope carries its own ``per_page``, which always wins;
#: this is only the fallback when a payload omits it.
PAGE_SIZE = 24

BROWSE_PATH = "/manga-list"
SEARCH_PATH = "/tim-kiem"
GENRE_PATH = "/genre"

#: Covers and page images both come from ``min.manhwa18.net``; the suffix
#: covers that subdomain and the apex, which serves the site's own assets.
IMAGE_HOST_SUFFIX = "manhwa18.net"

#: Separates the chapter key from the 1-based page index in a page id. Slugs
#: are lowercase alphanumerics and dashes, so a colon never occurs in one.
PAGE_ID_SEPARATOR = ":"

#: The Inertia payload attribute. Non-greedy up to the quote that closes the
#: attribute: the JSON inside is HTML-escaped, so it cannot contain a raw ``"``.
DATA_PAGE_RE = re.compile(r'data-page="(.*?)"\s*>', re.S)

CHAPTER_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")

#: Strips the ``<p>``/``<em>``/``<script>`` soup out of a ``pilot`` synopsis.
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.S | re.I)


# --- browse modes -----------------------------------------------------------

#: Mode id -> (label, ``sort`` query value). ``None`` sends no ``sort`` at all,
#: which is the site's own default ordering (most recently updated).
BROWSE_MODES: dict[str, tuple[str, str | None]] = {
    "default": ("Latest Updates", None),
    "new": ("Newly Added", "new"),
    "top": ("Most Popular", "top"),
}

DEFAULT_MODE = "default"

#: The site's own genre vocabulary, read from the ``genres`` prop that
#: ``/tim-kiem`` publishes. Hard-coded so ``list_genres`` costs no request.
GENRES: tuple[tuple[str, str], ...] = (
    ("action", "Action"), ("adult", "Adult"), ("adventure", "Adventure"),
    ("ai-art", "AI Art"), ("animal-characteristics", "Animal Characteristics"),
    ("art", "Art"), ("based-on-another-work", "Based on Another Work"),
    ("borderline-h", "Borderline H"), ("cohabitation", "Cohabitation"),
    ("collection-of-stories", "Collection of Stories"), ("comedy", "Comedy"),
    ("coworkers", "Coworkers"), ("crime", "Crime"), ("delinquents", "Delinquents"),
    ("demons", "Demons"), ("doujinshi", "Doujinshi"), ("drama", "Drama"),
    ("ecchi", "Ecchi"), ("explicit-sex", "Explicit Sex"), ("fantasy", "Fantasy"),
    ("fetish", "Fetish"), ("full-color", "Full Color"), ("ghosts", "Ghosts"),
    ("gl", "GL"), ("gyaru", "Gyaru"), ("harem", "Harem"),
    ("historical", "Historical"), ("horror", "Horror"), ("incest", "Incest"),
    ("isekai", "Isekai"), ("japanese-webtoons", "Japanese Webtoons"),
    ("magic", "Magic"), ("magical-girl", "Magical Girl"), ("manga", "Manga"),
    ("manhwa", "Manhwa"), ("mature", "Mature"), ("medical", "Medical"),
    ("monster-girls", "Monster Girls"), ("monsters", "Monsters"),
    ("mystery", "Mystery"), ("ntr", "NTR"), ("nudity", "Nudity"),
    ("psychological", "Psychological"), ("raw", "Raw"),
    ("reincarnation", "Reincarnation"), ("revenge", "Revenge"),
    ("reverse-harem", "Reverse Harem"), ("romance", "Romance"),
    ("salaryman", "Salaryman"), ("school-life", "School Life"),
    ("sci-fi", "Sci Fi"), ("seinen", "Seinen"), ("siblings", "Siblings"),
    ("slice-of-life", "Slice of Life"), ("smut", "Smut"), ("sports", "Sports"),
    ("summoned-into-another-world", "Summoned Into Another World"),
    ("supernatural", "Supernatural"), ("survival", "Survival"),
    ("thriller", "Thriller"), ("time-travel", "Time Travel"),
    ("uncensored", "Uncensored"), ("violence", "Violence"),
    ("webtoon", "Webtoon"), ("work-life", "Work Life"), ("yuri", "Yuri"),
)


def list_browse_modes() -> list[BrowseMode]:
    return [BrowseMode(id=key, label=label) for key, (label, _sort) in BROWSE_MODES.items()]


def list_genres() -> list[BrowseMode]:
    return [BrowseMode(id=slug, label=label) for slug, label in GENRES]


def normalize_sort(sort: str | None) -> str:
    if not sort:
        return DEFAULT_MODE
    return sort if sort in BROWSE_MODES else DEFAULT_MODE


def browse_params(sort: str | None, page: int) -> dict[str, Any]:
    _label, sort_value = BROWSE_MODES[normalize_sort(sort)]
    params: dict[str, Any] = {"page": max(page, 1)}
    if sort_value:
        params["sort"] = sort_value
    return params


def search_params(query: str, page: int, *, sort: str | None = None) -> dict[str, Any]:
    params = browse_params(sort, page)
    params["q"] = query.strip()
    return params


def genre_path(genre: str) -> str:
    return f"{GENRE_PATH}/{genre.strip().strip('/')}"


# --- identity ---------------------------------------------------------------


def _strip_site(value: str) -> str:
    text = html_lib.unescape(value or "").strip()
    for prefix in (f"{SITE_BASE}/", "https://manhwa18.net/", "http://manhwa18.net/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip("/")


def normalize_series_key(value: str) -> str:
    """``the-seed-of-destiny`` from any of the shapes the app may hand back."""
    text = _strip_site(value)
    if text.startswith("manga/"):
        text = text.removeprefix("manga/")
    return text.strip("/")


def normalize_chapter_key(value: str) -> str:
    """``the-seed-of-destiny/chapter-49`` from any inbound shape."""
    return normalize_series_key(value)


def series_path(series_key: str) -> str:
    return f"/manga/{normalize_series_key(series_key)}"


def chapter_path(chapter_key: str) -> str:
    return f"/manga/{normalize_chapter_key(chapter_key)}"


def make_chapter_key(series_key: str, chapter_slug: str) -> str:
    return f"{normalize_series_key(series_key)}/{chapter_slug.strip('/')}"


def make_page_id(chapter_key: str, number: int) -> str:
    return f"{chapter_key}{PAGE_ID_SEPARATOR}{number}"


def page_id_chapter_key(page_id: str) -> str | None:
    chapter_key, sep, _index = (page_id or "").rpartition(PAGE_ID_SEPARATOR)
    if not sep or not chapter_key:
        return None
    return chapter_key


def parse_chapter_number(label: str, *, fallback: float | None = None) -> float | None:
    """Chapter number from the site's own label ("Chapter 0 - Prologue" -> 0).

    Falls back to the payload's ``order`` when a label carries no digits at
    all, so every chapter this connector returns can be ordered -- an unset
    number would leave the reader unable to sequence the series.
    """
    match = CHAPTER_NUMBER_RE.search(label or "")
    if match is None:
        return fallback
    try:
        return float(match.group(1))
    except ValueError:
        return fallback


# --- payload ----------------------------------------------------------------


def inertia_props(html: str) -> dict[str, Any] | None:
    """The ``props`` object out of a page's Inertia payload."""
    match = DATA_PAGE_RE.search(html or "")
    if match is None:
        return None
    try:
        payload = json.loads(html_lib.unescape(match.group(1)))
    except (json.JSONDecodeError, ValueError):
        return None
    props = payload.get("props") if isinstance(payload, dict) else None
    return props if isinstance(props, dict) else None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _clean_html(value: Any) -> str | None:
    """Plain text out of a ``pilot`` synopsis.

    The field is author-entered HTML and several series append an inline
    ``<script>`` player bootstrap to it; stripping scripts before tags keeps
    that JavaScript source out of the description shown in the app.
    """
    if not value:
        return None
    text = SCRIPT_RE.sub(" ", str(value))
    text = TAG_RE.sub(" ", text)
    return _text(re.sub(r"\s+", " ", html_lib.unescape(text)))


def _genres(entries: Any) -> tuple[str, ...]:
    if not isinstance(entries, list):
        return ()
    return tuple(
        name
        for name in (_text(entry.get("name")) for entry in entries if isinstance(entry, dict))
        if name
    )


def _people(entries: Any) -> str | None:
    names = _genres(entries)
    return ", ".join(names) if names else None


def manga_to_series(item: dict[str, Any]) -> Series | None:
    """One paginator entry, or the detail page's ``manga`` object, as a Series.

    Both carry the same field names, so listing cards and the detail page
    share one mapper; the detail page simply fills in more of them.
    """
    slug = _text(item.get("slug"))
    title = _text(item.get("name"))
    if not slug or not title:
        return None

    latest = item.get("latest_chapter")
    latest_name = _text(latest.get("name")) if isinstance(latest, dict) else None
    if latest_name is None:
        chapters = item.get("latest_chapters")
        if isinstance(chapters, list) and chapters and isinstance(chapters[0], dict):
            latest_name = _text(chapters[0].get("name"))

    other_name = _text(item.get("other_name"))
    return Series(
        id=slug,
        title=title,
        canonical_path=series_path(slug),
        description=_clean_html(item.get("pilot")) or (other_name if other_name != title else None),
        cover_url=_text(item.get("cover_url")) or _text(item.get("thumb_url")),
        author=_people(item.get("translators")) or _people(item.get("owner")),
        artist=_people(item.get("artists")),
        # The payload carries a numeric ``status_id`` (0/1/2 observed) and no
        # label for it anywhere in the document, so any status string here
        # would be invented. Left unset rather than guessed.
        status=None,
        genres=_genres(item.get("genres")),
        latest_chapter=latest_name,
    )


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginator(props: dict[str, Any]) -> dict[str, Any] | None:
    """The Laravel paginator on a listing page, whichever key holds it.

    ``/manga-list`` and ``/genre/<slug>`` publish it as ``paginate``;
    ``/tim-kiem`` publishes the identical envelope as ``mangas``.
    """
    for key in ("paginate", "mangas"):
        value = props.get(key)
        if isinstance(value, dict) and isinstance(value.get("data"), list):
            return value
    return None


def parse_series_list(html: str, *, page: int) -> PaginatedSeriesList:
    props = inertia_props(html)
    envelope = paginator(props) if props else None
    if envelope is None:
        return PaginatedSeriesList(
            items=[], page=max(page, 1), page_size=PAGE_SIZE, total=0, api_has_more=False
        )

    items: list[Series] = []
    seen: set[str] = set()
    for entry in envelope["data"]:
        if not isinstance(entry, dict):
            continue
        series = manga_to_series(entry)
        if series is None or series.id in seen:
            continue
        seen.add(series.id)
        items.append(series)

    current = _int(envelope.get("current_page"), default=max(page, 1))
    last_page = _int(envelope.get("last_page"), default=0)
    return PaginatedSeriesList(
        items=items,
        page=current,
        page_size=_int(envelope.get("per_page"), default=PAGE_SIZE) or PAGE_SIZE,
        total=_int(envelope.get("total"), default=len(items)),
        api_has_more=bool(envelope.get("next_page_url")) or current < last_page,
    )


def parse_series_detail(html: str, series_key: str) -> Series | None:
    props = inertia_props(html)
    manga = props.get("manga") if props else None
    if not isinstance(manga, dict):
        return None
    series = manga_to_series(manga)
    if series is None:
        return None
    # Trust the requested key over the payload's own slug: the app stores the
    # key it was handed, and a redirect to a renamed slug must not silently
    # change a series' identity mid-session.
    return series if series.id == series_key else replace(series, id=series_key)


def parse_chapters(html: str, series_key: str) -> list[Chapter]:
    """Chapters from the series page, oldest-first.

    The payload lists them newest-first with an ``order`` field; the app wants
    ascending, and sorting on the parsed number keeps 28.1 < 28.2 < 29 right
    where a raw ``order`` sort would only reproduce the site's own sequence.
    """
    props = inertia_props(html)
    entries = props.get("chapters") if props else None
    if not isinstance(entries, list):
        return []

    chapters: list[Chapter] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        slug = _text(entry.get("slug"))
        title = _text(entry.get("name"))
        if not slug or not title:
            continue
        key = make_chapter_key(series_key, slug)
        if key in seen:
            continue
        seen.add(key)
        order = float(_int(entry.get("order"), default=len(chapters) + 1))
        chapters.append(
            Chapter(
                id=key,
                series_id=series_key,
                title=title,
                number=parse_chapter_number(title, fallback=order),
                # No per-chapter page count exists in this payload; the
                # connector backfills it from cache once a chapter is opened.
                page_count=0,
                release_date=_text(entry.get("created_at")),
            )
        )
    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0))
    return chapters


def parse_chapter_pages(html: str, chapter_key: str) -> list[Page]:
    props = inertia_props(html)
    images = props.get("chapterImages") if props else None
    if not isinstance(images, list):
        return []

    pages: list[Page] = []
    seen: set[str] = set()
    for entry in images:
        if not isinstance(entry, dict):
            continue
        url = _text(entry.get("src"))
        if not url or url in seen:
            continue
        seen.add(url)
        width = entry.get("source_width")
        height = entry.get("source_height")
        pages.append(
            Page(
                id=make_page_id(chapter_key, len(pages) + 1),
                chapter_id=chapter_key,
                number=len(pages) + 1,
                remote_url=url,
                # Present in the payload's schema but null on every chapter
                # measured, so the reader still measures its own layout.
                width=_int(width, default=0) or None,
                height=_int(height, default=0) or None,
            )
        )
    return pages
