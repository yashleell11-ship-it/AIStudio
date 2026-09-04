"""Map NovelBuddy's JSON API to normalized connector models.

NovelBuddy (https://novelbuddy.com -> https://novelbuddy.me) is a
daily-updated English web-novel / light-novel aggregator, the same family as
the existing ``freewebnovel`` and ``novelfull`` connectors. Probed FROM THE
VPS (production egress/TLS, 2026-09-04): every endpoint below answers 200
with plain httpx, no Cloudflare interstitial.

**Why the API and not the HTML.** The site is a Next.js app whose pages carry
their data in a ``__NEXT_DATA__`` blob, and that blob is fed by a public JSON
API at ``https://api.novelbuddy.me`` (the site publishes the host itself as
``siteConfig.apiUrl``, and its own bundle carries the route table). Reading
the API directly is one small JSON document per read instead of a ~200 KB
HTML page wrapped around the same fields, and it survives a front-end
redesign. Both hosts serve ``robots.txt`` with ``User-agent: * / Allow: /``
and disallow only ``/ads`` and ``/api/ads/`` — nothing this connector touches.

Endpoints used (all GET, all on ``api.novelbuddy.me``):

* Browse   -> ``/titles/search?page=N&sort=<sort>`` (no ``q`` at all — an
  EMPTY ``q`` is rejected with 400, so the parameter is omitted rather than
  blanked).
* Search   -> ``/titles/search?q=<query>&page=N``.
* Detail   -> ``/titles/<hsid>`` -> ``data.title``.
* Chapters -> ``/titles/<hsid>/chapters?limit=500`` -> ``data.chapters``.
  The endpoint returns the WHOLE list in one response (verified against a
  1,230-chapter title: ``limit`` is validated 1..500 but not applied as a
  slice, and ``pagination`` comes back ``null``), so a chapter list is
  always exactly ONE request.
* Chapter  -> ``/titles/<hsid>/chapters/<chapter hsid>`` ->
  ``data.chapter.content``, an HTML fragment.

Identity (house law: opaque, stored raw, never parsed by callers):

* ``series_key``  = ``"<hsid>/<slug>"``  (e.g. ``LDgamG8v/world-evolution-...``)
* ``chapter_key`` = ``"<hsid>/<slug>"``  (e.g. ``2Wz6RLKD/chapter-1-unlucky-day``)

Both deliberately contain a slash, exactly as Royal Road's keys do. The hsid
half is what the API addresses (a Sqid — the slug form is rejected with a 400
"Title ID must be a valid Sqid"); the slug half keeps the key readable and
round-trips to the site's own URL, ``https://novelbuddy.me/<slug>/<chslug>``.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

from connectors.ids import fully_unquote
from connectors.models import Chapter, NovelChapterText, PaginatedSeriesList, Series
from connectors.novel_text import (
    extract_paragraphs,
    hidden_classes_from_styles,
    normalize_line,
)

SITE_BASE = "https://novelbuddy.me"
API_BASE = "https://api.novelbuddy.me"

#: The API's own default page size for ``/titles/search``.
PAGE_SIZE = 20

#: ``limit`` is validated 1..500 upstream; 500 asks for "all of it" and the
#: endpoint obliges regardless of how many chapters the title really has.
CHAPTER_LIMIT = 500

#: Sort values the API accepts, mapped from our browse-mode ids. Anything
#: unknown falls back to ``views`` — an unrecognized sort is a 400 upstream,
#: so this dict is the allowlist, not a hint.
BROWSE_SORTS: dict[str, str] = {
    "": "views",
    "default": "views",
    "views": "views",
    "popular": "popular",
    "trending": "views_7days",
    "latest": "latest",
    "newest": "newest",
    "rating": "rating",
    "bookmarks": "bookmarks",
    "chapters": "chapters",
}

# --- aggregator junk --------------------------------------------------------

#: Watermark / self-promo lines specific to THIS site, applied on top of the
#: shared ``is_promo_line`` blacklist in ``connectors.novel_text`` (which
#: ``extract_paragraphs`` already runs). Every pattern here must be specific
#: enough that it can never fire on story prose: each one either names the
#: site, or requires a literal domain/URL token that narrative text does not
#: contain.
_SITE_PROMO_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # The site naming itself, however it is spaced or suffixed.
        r"\bnovel\s*buddy\b",
        # A bare URL or "www." domain sitting alone in a chapter body.
        r"\bhttps?://",
        r"\bwww\s*\.\s*[a-z0-9-]+\s*\.\s*(?:com|net|org|me|co|io)\b",
        # "read/continue this at <domain>" in any of its aggregator phrasings.
        r"(?:read|continue|find|follow)\b[^.]{0,40}\b(?:at|on)\s+[a-z0-9-]+\s*\.\s*"
        r"(?:com|net|org|me|co|io)\b",
        # "visit/bookmark our site", "support us on the website".
        r"\b(?:visit|bookmark|support)\b[^.]{0,30}\b(?:our|the)\s+"
        r"(?:site|website|page)\b",
        # "for more chapters, go to ..." / "latest chapters on ...".
        r"\b(?:more|latest|new)\s+chapters?\b[^.]{0,30}\b(?:at|on|from)\s+"
        r"[a-z0-9-]+\s*\.\s*(?:com|net|org|me|co|io)\b",
    )
)


def is_site_promo_line(paragraph: str) -> bool:
    """True when a paragraph is NovelBuddy watermark/self-promo, not story text."""
    normalized = normalize_line(paragraph).casefold()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _SITE_PROMO_PATTERNS)


# --- identity ---------------------------------------------------------------


def normalize_series_key(value: str) -> str:
    """``<hsid>/<slug>``, a site URL, or a bare hsid -> ``<hsid>/<slug>``."""
    cleaned = fully_unquote(value).strip().strip("/")
    if cleaned.startswith("http"):
        # https://novelbuddy.me/<slug> and .com both reduce to their tail.
        for host in ("novelbuddy.me/", "novelbuddy.com/"):
            if host in cleaned:
                cleaned = cleaned.split(host, 1)[-1].strip("/")
                break
    return cleaned


def normalize_chapter_key(value: str) -> str:
    """``<hsid>/<slug>``, a chapter URL, or a bare hsid -> ``<hsid>/<slug>``."""
    cleaned = fully_unquote(value).strip().strip("/")
    if cleaned.startswith("http"):
        for host in ("novelbuddy.me/", "novelbuddy.com/"):
            if host in cleaned:
                cleaned = cleaned.split(host, 1)[-1].strip("/")
                break
        # A chapter URL is /<series slug>/<chapter slug>; the series half is
        # not part of a chapter key.
        parts = cleaned.split("/")
        if len(parts) > 1:
            cleaned = parts[-1]
    return cleaned


def series_hsid(series_key: str) -> str:
    """The API-addressable half of a series key (a Sqid, never the slug)."""
    return normalize_series_key(series_key).split("/", 1)[0]


def series_slug(series_key: str) -> str:
    """The human-readable half of a series key; empty when the key is bare."""
    cleaned = normalize_series_key(series_key)
    return cleaned.split("/", 1)[1] if "/" in cleaned else ""


def chapter_hsid(chapter_key: str) -> str:
    """The API-addressable half of a chapter key."""
    return normalize_chapter_key(chapter_key).split("/", 1)[0]


def series_path(series_key: str) -> str:
    return f"/titles/{series_hsid(series_key)}"


def chapters_path(series_key: str) -> str:
    return f"/titles/{series_hsid(series_key)}/chapters"


def chapter_path(series_key: str, chapter_key: str) -> str:
    return f"/titles/{series_hsid(series_key)}/chapters/{chapter_hsid(chapter_key)}"


def browse_params(query: str | None, page: int, sort: str | None) -> dict[str, Any]:
    """Query string for ``/titles/search``.

    ``q`` is omitted entirely for a browse (an empty string is a 400:
    "Search query must be between 1 and 200 characters"), and the query is
    clipped to the 200 characters the API accepts rather than being rejected.
    """
    params: dict[str, Any] = {"page": max(1, page)}
    normalized = (query or "").strip()
    if normalized:
        params["q"] = normalized[:200]
    else:
        # Sort only matters for a browse; a search is relevance-ordered.
        params["sort"] = BROWSE_SORTS.get((sort or "").strip().lower(), "views")
    return params


# --- helpers ----------------------------------------------------------------


def _clean(text: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", text or "")).strip()


def _summary_text(summary: str | None) -> str | None:
    """Summaries arrive as HTML; store them as the same plain text as chapters."""
    if not summary:
        return None
    paragraphs = extract_paragraphs(summary)
    return "\n\n".join(paragraphs) or None


def _names(entries: Any) -> tuple[str, ...]:
    if not isinstance(entries, list):
        return ()
    out = []
    for entry in entries:
        if isinstance(entry, dict):
            name = _clean(str(entry.get("name") or ""))
            if name:
                out.append(name)
    return tuple(dict.fromkeys(out))


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _series_from_item(item: dict[str, Any]) -> Series | None:
    """One listing/detail record -> ``Series``, or None when unusable.

    House law: obviously-broken rows never reach clients. Here that means a
    record with no id, no title, or no evidence of a single chapter.
    """
    if not isinstance(item, dict):
        return None
    hsid = str(item.get("id") or "").strip()
    slug = str(item.get("slug") or "").strip()
    title = _clean(str(item.get("name") or ""))
    if not hsid or not title:
        return None

    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    chapter_count = int(stats.get("chapters_count") or 0)
    if chapter_count == 0:
        # Fall back to the recent-chapter teasers the listing carries; a
        # title with neither is a stub with nothing to read.
        latest = item.get("latest_chapters")
        chapter_count = len(latest) if isinstance(latest, list) else 0
    if chapter_count == 0:
        return None

    latest_chapters = item.get("latest_chapters")
    latest_name = None
    if isinstance(latest_chapters, list) and latest_chapters:
        first = latest_chapters[0]
        if isinstance(first, dict):
            latest_name = _clean(str(first.get("name") or "")) or None

    cover = str(item.get("cover") or "").strip() or None
    status = _clean(str(item.get("status") or "")).lower() or None
    authors = _names(item.get("authors"))

    return Series(
        id=f"{hsid}/{slug}" if slug else hsid,
        title=title,
        chapter_count=chapter_count,
        description=_summary_text(item.get("summary")),
        cover_url=cover,
        author=authors[0] if authors else None,
        status=status,
        genres=_names(item.get("genres")),
        latest_chapter=latest_name,
    )


# --- parsers ----------------------------------------------------------------


def parse_title_list(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    """``/titles/search`` -> a paginated listing."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return PaginatedSeriesList(items=[], page=page, page_size=PAGE_SIZE, total=0)

    raw_items = data.get("items")
    items: list[Series] = []
    if isinstance(raw_items, list):
        for entry in raw_items:
            series = _series_from_item(entry)
            if series is not None:
                items.append(series)

    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    page_size = int(pagination.get("limit") or PAGE_SIZE) or PAGE_SIZE
    total = int(pagination.get("total") or 0)
    has_next = pagination.get("has_next")
    return PaginatedSeriesList(
        items=items,
        page=int(pagination.get("page") or page),
        page_size=page_size,
        total=total,
        api_has_more=bool(has_next) if has_next is not None else None,
    )


def parse_title(payload: dict[str, Any], series_key: str) -> Series | None:
    """``/titles/<hsid>`` -> ``Series``, or None when the title is unusable."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    title = data.get("title")
    if not isinstance(title, dict):
        return None
    series = _series_from_item(title)
    if series is None:
        return None
    # Keep the caller's key: it is what the reader already holds, and the
    # upstream record may carry a redirect_slug that would silently rename it.
    normalized = normalize_series_key(series_key)
    if normalized and normalized != series.id:
        series = Series(
            id=normalized,
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


def parse_chapters(payload: dict[str, Any], series_key: str) -> list[Chapter]:
    """``/titles/<hsid>/chapters`` -> the full chapter list, oldest first.

    The API answers newest-first; the reader wants ascending order, so the
    list is sorted on the upstream ``number`` with the response order as the
    tie-break (a stable sort, so equal numbers keep their relative order).
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    raw = data.get("chapters")
    if not isinstance(raw, list):
        return []

    series_id = normalize_series_key(series_key)
    chapters: list[Chapter] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        hsid = str(entry.get("id") or "").strip()
        slug = str(entry.get("slug") or "").strip()
        title = _clean(str(entry.get("name") or ""))
        if not hsid or not title:
            continue
        chapters.append(
            Chapter(
                id=f"{hsid}/{slug}" if slug else hsid,
                series_id=series_id,
                title=title,
                number=_float_or_none(entry.get("number")),
                page_count=0,
                release_date=str(entry.get("updated_at") or "") or None,
            )
        )

    chapters.reverse()  # upstream is newest-first; ascending is the reading order
    chapters.sort(key=lambda ch: (ch.number is None, ch.number or 0.0))
    return chapters


def _drop_repeated_heading(paragraphs: list[str], title: str) -> list[str]:
    """Drop the chapter title where the body repeats it as its first line.

    Every NovelBuddy chapter body opens with its own title inside the content
    ``<div>`` — sometimes as bare text, sometimes wrapped in a ``<p>``. The
    reader already renders the title above the text, so leaving it in shows it
    twice (and a TTS pass would read it twice). Matching is exact against the
    normalized title, and only the FIRST paragraph is considered, so a chapter
    whose opening sentence merely resembles its title is never touched.
    """
    if not paragraphs or not title:
        return paragraphs
    wanted = normalize_line(title).casefold().rstrip(".:;,-— ")
    if not wanted:
        return paragraphs
    head = normalize_line(paragraphs[0]).casefold().rstrip(".:;,-— ")
    if head == wanted:
        return paragraphs[1:]
    return paragraphs


def parse_chapter(payload: dict[str, Any]) -> NovelChapterText | None:
    """``/titles/<hsid>/chapters/<hsid>`` -> sanitized plain-text paragraphs.

    Three cleanup layers run here: the shared structural strip and promo
    blacklist inside ``extract_paragraphs``, this site's own watermark
    patterns (``is_site_promo_line``), and the duplicated-heading drop.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    chapter = data.get("chapter")
    if not isinstance(chapter, dict):
        return None
    content = chapter.get("content")
    if not isinstance(content, str) or not content.strip():
        return None

    paragraphs = extract_paragraphs(
        content, hidden_classes=hidden_classes_from_styles(content)
    )
    paragraphs = [p for p in paragraphs if not is_site_promo_line(p)]

    title = _clean(str(chapter.get("name") or ""))
    paragraphs = _drop_repeated_heading(paragraphs, title)
    if not paragraphs:
        return None

    return NovelChapterText(
        title=title,
        paragraphs=tuple(paragraphs),
        chapter_number=_float_or_none(chapter.get("number")),
    )
