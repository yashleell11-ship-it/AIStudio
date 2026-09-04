"""Source-native reader service (spec §4.1, §5.2).

There are no local chapters any more — every read goes through a connector with
the caller's own request context. This service does three things:

* ``manifest()`` — the client's *download plan* for a chapter: the ordered page
  list (number + proxy URL), chapter number, and prev/next chapter keys. No
  bytes.
* ``manifest_batch()`` — the same plan for a bounded WINDOW of chapters, for
  Read-all and multi-chapter download (spec 2026-09-05-reading-flow-design
  R2/R4). Same guarantees per chapter, one round trip for the client.
* ``resolve_source_chapter()`` — the online reader payload (the old online path,
  minus the deleted "local copy shortcut" branch).

Reading position, bookmarks and history live in ``progress_service``.
"""

from __future__ import annotations

from typing import Annotated, Any, Sequence

from fastapi import Depends
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.config import get_settings
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.bulk_fetch import item_error, map_bounded
from services.source_cache_service import SourceCacheService


def _chapter_key(entry: dict[str, Any]) -> str:
    """The chapter's key, whichever shape the entry arrived in.

    A connector serializes chapters with ``id``; ``source_series_cache`` stores
    them with ``key`` (see ``SourceCacheService._merge_series_row``). Both are
    the same value, and this service now reads from either source.
    """
    return str(entry.get("id") or entry.get("key") or "")


def _locate(chapters: list[dict[str, Any]], chapter_key: str) -> int:
    """Index of ``chapter_key`` in ``chapters``, or -1.

    Exact match first, then ignoring surrounding slashes — connectors are not
    consistent about leading/trailing separators in chapter ids.
    """
    keys = [_chapter_key(c) for c in chapters]
    try:
        return keys.index(chapter_key)
    except ValueError:
        target = chapter_key.strip("/")
        return next(
            (i for i, k in enumerate(keys) if k.strip("/") == target), -1
        )


class ReaderService:
    def __init__(
        self,
        browse: BrowseService,
        *,
        db: Session | None = None,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._browse = browse
        # Optional so a caller with no session (tests, scripts) still gets a
        # working reader — it simply goes to the connector every time, which is
        # what this service did unconditionally before.
        self._cache = SourceCacheService(db, browse) if db is not None else None
        self._user_id = user_id
        self._profile_id = profile_id

    def _chapters(
        self, source_id: str, series_key: str, *, force: bool = False
    ) -> list[dict[str, Any]]:
        """The series' chapter list, from ``source_series_cache`` when it can be.

        This is the single most expensive thing the reader did. ``manifest``
        needs the chapter list only to locate the chapter and name its
        neighbours, but it asked the *connector* for it — and
        ``BrowseService.get_chapters`` fetches the series page upstream first.
        Measured against the owner's own asurascans follows on the VPS, that
        cost 272 ms and 355 ms per chapter open against ~1 ms from the cache.
        The connector keeps its own 180-second in-process cache, so consecutive
        chapters of one series were cheap, but the first chapter of a session,
        anything after a container restart, and any pause longer than three
        minutes all paid full price.

        ``force`` bypasses the cached row; see ``manifest`` for the one case
        that needs it.
        """
        if self._cache is None:
            return self._browse.get_chapters(source_id, series_key)
        return self._cache.get_chapter_list(source_id, series_key, force=force)

    def resolve_source_chapter(
        self,
        source_id: str,
        series_key: str,
        chapter_key: str,
    ) -> dict[str, Any]:
        """Online reader payload straight from the connector."""
        return self._browse.get_reader_chapter(
            source_id,
            fully_unquote(series_key),
            fully_unquote(chapter_key),
        )

    def _resolve_chapter_list(
        self, source_id: str, series_key: str, wanted: Sequence[str]
    ) -> list[dict[str, Any]]:
        """The chapter list, refetched live once if any ``wanted`` key is absent.

        The cached list is up to ``source_cache_ttl_minutes`` old (6 hours), so
        a chapter published since it was written is legitimately absent. That is
        worth a live fetch: without this retry, serving the reader from cache
        would 404 exactly the newest chapter — the one the owner is most likely
        to be opening.

        An *empty* cached list gets the same retry, and that is not an edge
        case: ``get_series_meta`` treats a row holding ``[]`` as a fresh hit, so
        one upstream blip that answered with no chapters would otherwise make
        the reader insist the series does not exist for the rest of the TTL.
        Before this service read from the cache it went to the connector every
        time and was immune to that; the retry is what keeps the speedup from
        changing the answer. The cost is one upstream fetch on a genuine 404,
        which is rare, and ``force=True`` still falls back to the stale row if
        the connector is down.

        ONE retry covers the whole window, not one per missing chapter: a
        Read-all window asking for twenty chapters that a stale list is missing
        must not become twenty series-page scrapes.
        """
        chapters = self._chapters(source_id, series_key)
        if self._cache is not None and any(
            _locate(chapters, key) < 0 for key in wanted
        ):
            chapters = self._chapters(source_id, series_key, force=True)
        return chapters

    @staticmethod
    def _require_index(chapters: list[dict[str, Any]], chapter_key: str) -> int:
        if not chapters:
            raise AppError(
                "Series not found.", code="series_not_found", status_code=404
            )
        idx = _locate(chapters, chapter_key)
        if idx < 0:
            raise AppError(
                "Chapter not found.", code="chapter_not_found", status_code=404
            )
        return idx

    @staticmethod
    def _assemble(
        source_id: str,
        series_key: str,
        chapter_key: str,
        chapters: list[dict[str, Any]],
        idx: int,
        pages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build one manifest payload from an already-resolved list + pages.

        Pure and DB-free, so the batch path can call it on the request thread
        with page lists its workers fetched. The single and bulk endpoints
        therefore serve byte-identical per-chapter payloads by construction, not
        by two implementations agreeing.
        """
        keys = [_chapter_key(c) for c in chapters]
        chapter = chapters[idx]
        return {
            "source_id": source_id,
            "series_key": series_key,
            "chapter_key": chapter_key,
            "chapter_number": chapter.get("number"),
            "page_count": len(pages),
            "pages": [
                {"number": p["number"], "url": p["image_url"]} for p in pages
            ],
            "prev": keys[idx - 1] if idx > 0 else None,
            "next": keys[idx + 1] if idx < len(keys) - 1 else None,
        }

    def manifest(
        self,
        source_id: str,
        series_key: str,
        chapter_key: str,
    ) -> dict[str, Any]:
        """The download plan for one chapter (spec §4.1).

        ``{ page_count, chapter_number, pages: [{number, url}], prev, next }``.
        ``url`` points at the existing image proxy. ``sha256``/``size`` are
        omitted for v1 (open question O-1) — the client content-addresses by
        hashing what it downloads.
        """
        series_key = fully_unquote(series_key)
        chapter_key = fully_unquote(chapter_key)

        # Per-caller gate FIRST, before anything is read. This used to be
        # implicit: the chapter list came from ``BrowseService.get_chapters``,
        # which resolves the connector and so applied the 18+ gate before the
        # method could say anything else. Serving that list from
        # ``source_series_cache`` skips the connector entirely — cache rows are
        # global, and whether *this* caller may see the source is not — which
        # left a gated caller able to tell a cached mature source
        # (``chapter_not_found``) from one that was never installed
        # (``source_not_found``). Costs no network; same call
        # ``SourceCacheService.get_browse_page`` makes for the same reason.
        self._browse.ensure_visible(source_id)

        chapters = self._resolve_chapter_list(source_id, series_key, (chapter_key,))
        idx = self._require_index(chapters, chapter_key)
        pages = self._browse.get_chapter_pages(source_id, chapter_key)
        return self._assemble(
            source_id, series_key, chapter_key, chapters, idx, pages
        )

    def manifest_batch(
        self,
        source_id: str,
        series_key: str,
        chapter_keys: Sequence[str],
    ) -> dict[str, Any]:
        """Manifests for a bounded WINDOW of chapters of one series (R2/R4).

        Read-all opening a 300-chapter series one manifest at a time is 300
        round trips before the reader can plan anything, and 300 series-page
        scrapes upstream if the chapter-list cache ever misses. This is the same
        work in one request: the chapter list is resolved ONCE, the 18+ gate is
        applied once up front and again per chapter inside
        ``BrowseService.get_chapter_pages``, and only the genuinely per-chapter
        part (the page list) fans out.

        Guarantees held identical to the single manifest, on purpose — a bulk
        path that quietly relaxes one of them is the bug that shipped here:

        * **18+ gate** — ``ensure_visible`` before any cache is read, so a
          window cannot become an oracle for "this mature source is cached".
        * **profile scoping** — the gate value is the one
          ``get_browse_service`` resolved from this request's
          ``(user_id, profile_id)``; nothing here re-reads settings.
        * **source cache** — the chapter list still comes from
          ``source_series_cache``, once for the window rather than once per
          chapter.

        Degrades per chapter: an upstream failure on chapter 7 of 20 returns 19
        manifests and one ``error`` item, never a 500 for the window. The window
        itself fails only for things that are true of the whole request — an
        invisible source, an unresolvable series, an over-cap window.
        """
        series_key = fully_unquote(series_key)
        keys = [fully_unquote(key) for key in chapter_keys]

        cap = bulk_manifest_cap()
        if len(keys) > cap:
            raise AppError(
                "Too many chapters in one window.",
                code="batch_too_large",
                status_code=413,
                details={"max_chapters": cap, "received": len(keys)},
            )

        # Same first line as ``manifest``, same reason, and it must stay first:
        # everything below reads a cache whose rows are global.
        self._browse.ensure_visible(source_id)

        chapters = self._resolve_chapter_list(source_id, series_key, keys)
        if not chapters:
            # Nothing can be identified without the list — chapter_number and
            # prev/next are the manifest. Whole-window failure, exactly the
            # error the single manifest gives.
            raise AppError(
                "Series not found.", code="series_not_found", status_code=404
            )

        located = [_locate(chapters, key) for key in keys]

        # One fetch per DISTINCT resolvable key. A client repeating a key in a
        # window (a re-request stitched onto a prefetch, say) must not double
        # the upstream cost.
        fetch_keys: list[str] = []
        for position, key in enumerate(keys):
            if located[position] >= 0 and key not in fetch_keys:
                fetch_keys.append(key)

        def _pages(key: str) -> list[dict[str, Any]]:
            # Network only — no session touched on a worker thread.
            return self._browse.get_chapter_pages(source_id, key)

        outcomes = dict(zip(fetch_keys, map_bounded(fetch_keys, _pages)))

        items: list[dict[str, Any]] = []
        for position, key in enumerate(keys):
            idx = located[position]
            if idx < 0:
                items.append(
                    {
                        "chapter_key": key,
                        "status": "error",
                        "manifest": None,
                        "error": {
                            "code": "chapter_not_found",
                            "status": 404,
                            "message": "Chapter not found.",
                        },
                    }
                )
                continue
            outcome = outcomes[key]
            if isinstance(outcome, BaseException):
                items.append(
                    {
                        "chapter_key": key,
                        "status": "error",
                        "manifest": None,
                        "error": item_error(source_id, outcome),
                    }
                )
                continue
            items.append(
                {
                    "chapter_key": key,
                    "status": "ok",
                    "manifest": self._assemble(
                        source_id, series_key, key, chapters, idx, outcome
                    ),
                    "error": None,
                }
            )

        ok_count = sum(1 for item in items if item["status"] == "ok")
        return {
            "source_id": source_id,
            "series_key": series_key,
            # Echoed on every response so a client pages by the server's stride
            # instead of hard-coding one that a config change would break.
            "max_chapters": cap,
            "requested": len(items),
            "ok_count": ok_count,
            "failed_count": len(items) - ok_count,
            "items": items,
        }


def bulk_manifest_cap() -> int:
    """Chapters per bulk-manifest window. ``MM_READER_BULK_MAX_CHAPTERS``.

    Read at call time, not import time, so a deployment can retune the window
    without a code change — and echoed in every bulk response as
    ``max_chapters`` so clients page by whatever it currently is.
    """
    try:
        return max(1, int(getattr(get_settings(), "reader_bulk_max_chapters", 20)))
    except (TypeError, ValueError):
        return 20


def get_reader_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> ReaderService:
    return ReaderService(
        browse, db=db, user_id=ctx.user_id, profile_id=ctx.profile_id
    )
