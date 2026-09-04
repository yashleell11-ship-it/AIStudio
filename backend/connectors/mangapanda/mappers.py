"""Map MangaPanda HTML pages to normalized connector models.

MangaPanda is a server-rendered React app: every listing, the full chapter
list, and every chapter's page images arrive complete in the initial HTML,
so each connector stage costs exactly one GET and no endpoint needs a
second round trip.

Two site quirks drive the parsing here:

* React's SSR splits interpolated text with empty HTML comments, so the
  markup reads ``#<!-- -->886`` and ``- <!-- -->Chapter 886``. Every parse
  entry point strips comments first, which rejoins those into ``#886`` and
  ``- Chapter 886``.
* Class names are hashed CSS-module identifiers (``_3pfyN``, ``_287KE``)
  that change whenever the site rebuilds its bundle. Nothing here keys off
  one. The anchors used instead are the stable, semantic ones: Bootstrap's
  ``media-manga``/``media-heading``/``list-group-item``, the site's own
  ``manga-thumb`` and ``genre-label``, the ``/manga/`` and ``/chapter/``
  URL shapes, and the literal field labels (``Author``, ``Status``).
"""

from __future__ import annotations

import html as html_module
import re

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://mangapanda.onl"

#: Every listing view on this site renders 30 cards per page.
PAGE_SIZE = 30

#: Browse mode id -> listing path segment. The site exposes each of these as
#: its own top-level route; ``search`` with no query is the A-Z directory.
SORT_TO_SEGMENT: dict[str, str] = {
    "default": "updates",
    "popular": "popular",
    "added": "new",
    "completed": "completed",
    "alphabetical": "search",
}

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# Anchors may be written absolute (https://mangapanda.onl/manga/x) or rooted
# (/manga/x); both forms appear in the same document.
_HREF_PREFIX = r'(?:https?://[^"]*?)?'

_CARD_MARKER = '<div class="media-manga media">'

_CARD_LINK_RE = re.compile(rf'href="{_HREF_PREFIX}/manga/([^"?#]+)"', re.I)
_CARD_HEADING_RE = re.compile(
    r'<h4[^>]*class="[^"]*media-heading[^"]*"[^>]*>(.*?)</h4>', re.S | re.I
)
_CARD_TITLE_LINK_RE = re.compile(
    rf'href="{_HREF_PREFIX}/manga/[^"?#]+"[^>]*>(.*?)</a>', re.S | re.I
)
_CARD_AUTHOR_RE = re.compile(r"<small[^>]*>\s*by\s+(.*?)</small>", re.S | re.I)
_THUMB_RE = re.compile(
    r'<img[^>]+src="([^"]+)"[^>]*class="[^"]*manga-thumb[^"]*"', re.I
)
_CARD_STATUS_RE = re.compile(r"chapters published\s*\(([^)<]+)\)", re.I)
_GENRE_RE = re.compile(
    r'class="[^"]*genre-label[^"]*"[^>]*>([^<]+)</a>', re.I
)
_GENRE_HREF_RE = re.compile(
    rf'href="{_HREF_PREFIX}/genre/([^"?#/]+)"[^>]*class="[^"]*genre-label[^"]*"[^>]*>([^<]+)</a>',
    re.I,
)

#: The pager renders a ``next`` list item only while another page exists.
#: That presence is the site's own has-more signal — it publishes no total.
_NEXT_PAGE_RE = re.compile(r'<li[^>]*class="[^"]*\bnext\b[^"]*"', re.I)

_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
#: Alternative titles and the "Hot" badge are nested inside the <h1>; both
#: must come out before the heading text is read.
_H1_NOISE_RE = re.compile(r"<(a|small)\b.*?</\1>", re.S | re.I)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', re.I
)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', re.I
)
_SUMMARY_RE = re.compile(
    r'id="chapters-tab-pane-999".*?<p[^>]*>(.*?)</p>', re.S | re.I
)
_CHAPTER_LIST_START_RE = re.compile(r'<ul[^>]*class="[^"]*list-group[^"]*"', re.I)


def _field_re(label: str) -> re.Pattern[str]:
    return re.compile(rf">{label}</span>\s*<span[^>]*>(.*?)</span>", re.S | re.I)


_AUTHOR_FIELD_RE = _field_re("Author")
_ARTIST_FIELD_RE = _field_re("Artist")
_STATUS_FIELD_RE = _field_re("Status")

_LI_RE = re.compile(
    r'<li[^>]*class="[^"]*list-group-item[^"]*"[^>]*>(.*?)</li>', re.S | re.I
)
_CHAPTER_ANCHOR_RE = re.compile(
    rf'<a\s[^>]*href="{_HREF_PREFIX}/chapter/([^"?#]+)"[^>]*>(.*?)</a>', re.S | re.I
)
_CHAPTER_NUMBER_RE = re.compile(r">#\s*([0-9]+(?:\.[0-9]+)?)\s*<")
_CHAPTER_TITLE_RE = re.compile(r">\s*-\s*([^<]*)</span>")
_CHAPTER_DATE_RE = re.compile(r"<small[^>]*>([^<]*)</small>", re.I)
_KEY_NUMBER_RE = re.compile(r"chapter-([0-9]+(?:\.[0-9]+)?)$", re.I)

#: A chapter page image always lives at ``<slug>/<chapter>/<n>.<ext>`` — the
#: final path component is purely the page number. Cover art on the same CDN
#: ends in a title slug (``thumb.mghcdn.com/mr/kingdom.jpg``), so requiring a
#: numeric filename is what keeps the trailing "Popular Updates" carousel
#: thumbnails out of the page list.
_PAGE_IMAGE_RE = re.compile(
    r'<img[^>]+src="(https?://[^"]+/\d+\.(?:png|jpe?g|webp|avif))"', re.I
)


def strip_comments(markup: str) -> str:
    """Remove HTML comments, rejoining React's split text nodes."""
    return _COMMENT_RE.sub("", markup)


def _clean_text(value: str) -> str:
    return html_module.unescape(re.sub(r"\s+", " ", _TAG_RE.sub(" ", value))).strip()


def normalize_sort(sort: str | None) -> str:
    """Map a browse mode id onto the site's listing path segment."""
    if not sort:
        return SORT_TO_SEGMENT["default"]
    return SORT_TO_SEGMENT.get(sort, SORT_TO_SEGMENT["default"])


def listing_path(page: int, *, sort: str | None = None) -> str:
    segment = normalize_sort(sort)
    if page <= 1:
        return f"/{segment}"
    return f"/{segment}/page/{page}"


def genre_path(genre: str, page: int) -> str:
    slug = genre.strip().strip("/")
    if page <= 1:
        return f"/genre/{slug}"
    return f"/genre/{slug}/page/{page}"


def search_path() -> str:
    return "/search"


def search_params(query: str) -> dict[str, str]:
    return {"q": query.strip()}


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/chapter/{chapter_id.strip().strip('/')}"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    """Split a page id back into its chapter key.

    Chapter keys contain slashes and dots but never a colon, so the last
    colon is an unambiguous separator.
    """
    if ":" not in page_id:
        return None
    chapter_id, _, _number = page_id.rpartition(":")
    return chapter_id or None


def _as_number(raw: str) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return int(value) if value.is_integer() else value


def has_next_page(markup: str) -> bool:
    return _NEXT_PAGE_RE.search(markup) is not None


def _split_cards(markup: str) -> list[str]:
    parts = markup.split(_CARD_MARKER)
    return parts[1:] if len(parts) > 1 else []


def parse_series_cards(markup: str) -> list[Series]:
    """Parse the ``media-manga`` cards every listing and search page renders."""
    body = strip_comments(markup)
    items: list[Series] = []
    seen: set[str] = set()
    for block in _split_cards(body):
        link = _CARD_LINK_RE.search(block)
        if link is None:
            continue
        series_id = link.group(1).strip("/")
        if not series_id or series_id in seen:
            continue

        heading = _CARD_HEADING_RE.search(block)
        title = ""
        author = None
        if heading is not None:
            inner = heading.group(1)
            title_link = _CARD_TITLE_LINK_RE.search(inner)
            if title_link is not None:
                title = _clean_text(title_link.group(1))
            author_match = _CARD_AUTHOR_RE.search(inner)
            if author_match is not None:
                author = _clean_text(author_match.group(1)) or None
        if not title:
            # Cards always carry the title on the thumbnail's alt attribute
            # too; falling back to it keeps a card whose heading markup
            # changed from vanishing out of the listing entirely.
            thumb_alt = re.search(
                r'<img[^>]+alt="([^"]*)"[^>]*class="[^"]*manga-thumb[^"]*"', block, re.I
            )
            title = _clean_text(thumb_alt.group(1)) if thumb_alt else series_id
        if not title:
            continue

        seen.add(series_id)
        thumb = _THUMB_RE.search(block)
        status = _CARD_STATUS_RE.search(block)
        genres = tuple(
            dict.fromkeys(_clean_text(name) for name in _GENRE_RE.findall(block))
        )
        items.append(
            Series(
                id=series_id,
                title=title,
                canonical_path=series_id_to_path(series_id),
                cover_url=thumb.group(1) if thumb else None,
                author=author,
                status=_clean_text(status.group(1)) if status else None,
                genres=genres,
            )
        )
    return items


def _listing(
    items: list[Series], *, page: int, has_more: bool, page_size: int = PAGE_SIZE
) -> PaginatedSeriesList:
    # The site publishes no result count anywhere — only a next-page link. The
    # total reported here is therefore an honest lower bound (everything seen
    # so far, plus one more page when the pager says there is one) rather than
    # an invented figure.
    consumed = (page - 1) * page_size + len(items)
    total = consumed + page_size if has_more else consumed
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_series_list(markup: str, *, page: int) -> PaginatedSeriesList:
    body = strip_comments(markup)
    return _listing(parse_series_cards(body), page=page, has_more=has_next_page(body))


def parse_search_results(markup: str, *, page: int) -> PaginatedSeriesList:
    """Parse a ``/search?q=`` result page.

    Search answers on a single page — it renders an empty pager and ignores
    a page parameter — so ``has_more`` is always False here.
    """
    return _listing(parse_series_cards(markup), page=page, has_more=False)


def _detail_head(body: str) -> str:
    """The metadata block above the chapter list.

    Genre chips and thumbnails also appear in the "Popular Manga Updates"
    carousel further down every series page; slicing the header off first is
    what stops that carousel's genres and covers being read as this series'.
    """
    start = body.find('id="mangadetail"')
    if start < 0:
        start = 0
    list_start = _CHAPTER_LIST_START_RE.search(body, start)
    return body[start : list_start.start()] if list_start else body[start:]


def parse_series_detail(markup: str, series_id: str) -> Series | None:
    body = strip_comments(markup)
    head = _detail_head(body)

    title = ""
    h1 = _H1_RE.search(head)
    if h1 is not None:
        title = _clean_text(_H1_NOISE_RE.sub("", h1.group(1)))
    if not title:
        og = _OG_TITLE_RE.search(body)
        if og is None:
            return None
        # og:title is phrased "Read <Title> Manga Online for Free".
        title = _clean_text(og.group(1))
        title = re.sub(r"^Read\s+", "", title, flags=re.I)
        title = re.sub(r"\s+Manga Online for Free$", "", title, flags=re.I)
    if not title:
        return None

    thumb = _THUMB_RE.search(head)
    author = _AUTHOR_FIELD_RE.search(head)
    artist = _ARTIST_FIELD_RE.search(head)
    status = _STATUS_FIELD_RE.search(head)
    genres = tuple(dict.fromkeys(_clean_text(name) for name in _GENRE_RE.findall(head)))

    description = None
    summary = _SUMMARY_RE.search(body)
    if summary is not None:
        description = _clean_text(summary.group(1)) or None
    if not description:
        og_desc = _OG_DESC_RE.search(body)
        if og_desc is not None:
            description = _clean_text(og_desc.group(1)) or None

    return Series(
        id=series_id,
        title=title,
        canonical_path=series_id_to_path(series_id),
        cover_url=thumb.group(1) if thumb else None,
        description=description,
        author=_clean_text(author.group(1)) if author else None,
        artist=_clean_text(artist.group(1)) if artist else None,
        status=_clean_text(status.group(1)) if status else None,
        genres=genres,
    )


def _pick_chapter_anchor(
    anchors: list[tuple[str, str]]
) -> tuple[str, str] | None:
    """Choose the canonical anchor among a row's links.

    Rows for chapters that also exist in an alternate (e.g. full-colour)
    edition render two anchors under one displayed number. Only the canonical
    one carries the release date, and the alternate's href holds an unrelated
    internal id (``chapter-121113.5`` sitting under a ``#9.1`` heading), so
    picking by the date is what keeps the stored key pointing at the chapter
    the number claims.
    """
    if not anchors:
        return None
    for key, inner in anchors:
        if "<small" in inner.lower():
            return key, inner
    return anchors[-1]


def parse_chapters(markup: str, series_id: str) -> list[Chapter]:
    body = strip_comments(markup)
    prefix = f"{series_id.strip('/')}/"
    chapters: list[Chapter] = []
    seen: set[str] = set()

    for row in _LI_RE.findall(body):
        anchors = [
            (key.strip("/"), inner)
            for key, inner in _CHAPTER_ANCHOR_RE.findall(row)
            # Every series page also lists other series' newest chapters in
            # its sidebar and carousel; the prefix check drops those.
            if key.strip("/").startswith(prefix)
        ]
        picked = _pick_chapter_anchor(anchors)
        if picked is None:
            continue
        chapter_id, inner = picked
        if chapter_id in seen:
            continue
        seen.add(chapter_id)

        number_match = _CHAPTER_NUMBER_RE.search(inner)
        number = _as_number(number_match.group(1)) if number_match else None
        if number is None:
            key_match = _KEY_NUMBER_RE.search(chapter_id)
            number = _as_number(key_match.group(1)) if key_match else None

        title_match = _CHAPTER_TITLE_RE.search(inner)
        title = _clean_text(title_match.group(1)) if title_match else ""
        if not title:
            title = f"Chapter {number}" if number is not None else chapter_id

        date_match = _CHAPTER_DATE_RE.search(inner)
        release_date = _clean_text(date_match.group(1)) if date_match else None

        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=title,
                number=number,
                # The series page carries no per-chapter page count; the
                # connector backfills it from cache once a chapter is read.
                page_count=0,
                release_date=release_date or None,
            )
        )

    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0))
    return chapters


def parse_chapter_pages(markup: str, chapter_id: str) -> list[Page]:
    body = strip_comments(markup)
    urls = list(dict.fromkeys(_PAGE_IMAGE_RE.findall(body)))
    return [
        Page(
            id=make_page_id(chapter_id, index),
            chapter_id=chapter_id,
            number=index,
            remote_url=url,
        )
        for index, url in enumerate(urls, start=1)
    ]


def parse_genres(markup: str) -> list[tuple[str, str]]:
    """Return ``(slug, label)`` for every genre chip on a page."""
    body = strip_comments(markup)
    found: dict[str, str] = {}
    for slug, label in _GENRE_HREF_RE.findall(body):
        slug = slug.strip().lower()
        if slug and slug not in found:
            found[slug] = _clean_text(label)
    return sorted(found.items())


#: The site's full genre vocabulary, captured from the ``/search`` directory's
#: own filter chips. Held statically so ``list_genres`` — which the browse UI
#: calls on every source open — costs no request at all.
GENRE_SLUGS: tuple[str, ...] = (
    "action", "adaptation", "adventure", "animals", "award-winning", "comedy",
    "cooking", "crime", "demons", "drama", "ecchi", "erotica", "fantasy",
    "full-color", "ghosts", "gore", "harem", "historical", "horror", "isekai",
    "loli", "long-strip", "magic", "manga", "manhua", "manhwa", "martial-arts",
    "mature", "military", "monster-girls", "monsters", "mystery", "ninja",
    "philosophical", "police", "post-apocalyptic", "psychological",
    "reincarnation", "romance", "safe", "samurai", "school-life", "sci-fi",
    "seinen", "sexual-violence", "shounen", "slice-of-life", "sports",
    "suggestive", "superhero", "supernatural", "survival", "thriller",
    "time-travel", "tragedy", "vampires", "video-games", "web-comic",
    "webtoons", "wuxia",
)

_GENRE_LABEL_OVERRIDES = {
    "sci-fi": "Sci-fi",
    "award-winning": "Award winning",
    "full-color": "Full color",
    "post-apocalyptic": "Post-apocalyptic",
    "slice-of-life": "Slice of Life",
    "school-life": "School Life",
    "martial-arts": "Martial Arts",
    "monster-girls": "Monster Girls",
    "sexual-violence": "Sexual Violence",
    "time-travel": "Time Travel",
    "video-games": "Video Games",
    "web-comic": "Web Comic",
    "long-strip": "Long Strip",
}


def genre_label(slug: str) -> str:
    override = _GENRE_LABEL_OVERRIDES.get(slug)
    if override:
        return override
    return slug.replace("-", " ").title()
