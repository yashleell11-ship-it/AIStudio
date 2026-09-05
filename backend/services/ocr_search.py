"""Dialogue search over OCR-extracted chapter text (spec §4.4).

``chapter_ocr`` is global, but a search result is only returned when the caller
*follows* that series (in the active profile) and the 18+ gate allows it — so
one profile can never see another's OCR contribution for a series it does not
follow.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.profile_context import ProfileContext, resolve_profile_context
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.followed_series_service import FollowedSeriesService
from utils.api_pagination import enrich_pagination_aliases


def terms_of(raw: str) -> list[str]:
    """The query's terms, in order. Also drives snippet highlighting, so the
    two can never disagree about what was searched for."""
    return [t for t in re.split(r"\s+", raw.strip()) if t]


def match_expr(raw: str) -> str:
    """The FTS5 ``MATCH`` expression for a free-text query.

    Every whitespace-separated term becomes a quoted FTS5 string so that
    punctuation a reader types (``!``, ``-``, ``*``, ``:``) is matched
    literally instead of being parsed as query syntax. The quoting is only
    safe if the term's OWN double quotes are escaped first, by doubling them
    the way SQL string literals do: ``he"llo`` wrapped naively is
    ``"he"llo"``, an unterminated FTS5 string, and SQLite answers the whole
    request with ``OperationalError: unterminated string`` — a 500 on exactly
    the query someone searching for a remembered line of dialogue types.
    """
    return " ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in terms_of(raw))


class OcrSearchService:
    def __init__(
        self,
        db: Session,
        followed: FollowedSeriesService,
    ) -> None:
        self._db = db
        self._followed = followed

    def _allowed_series(self) -> set[tuple[str, str]] | None:
        """The ``(source_id, series_key)`` pairs the caller may see OCR for.

        ``None`` when there is no caller context (unscoped) — nothing is
        allowed, search returns empty.
        """
        if self._followed._user_id is None:
            return None
        rows = self._followed.list_series(page=1, per_page=10_000)["items"]
        return {(r["source_id"], r["series_key"]) for r in rows}

    def search(
        self, query: str, *, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        raw = (query or "").strip()
        allowed = self._allowed_series()
        if not raw or not allowed:
            return enrich_pagination_aliases(
                {"items": [], "total": 0, "offset": offset, "limit": limit}
            )

        terms = terms_of(raw)
        expression = match_expr(raw)

        rows = self._db.execute(
            text(
                """
                SELECT c.id, c.source_id, c.series_key, c.chapter_key,
                       c.full_text, c.word_count, c.engine
                FROM chapter_ocr_fts f
                JOIN chapter_ocr c ON c.id = f.rowid
                WHERE chapter_ocr_fts MATCH :q
                ORDER BY c.word_count DESC
                """
            ),
            {"q": expression},
        ).all()

        filtered = [
            r for r in rows if (r.source_id, r.series_key) in allowed
        ]
        total = len(filtered)
        window = filtered[offset : offset + limit]

        lowered_terms = [t.lower() for t in terms]
        items = [
            {
                "source_id": r.source_id,
                "series_key": r.series_key,
                "chapter_key": r.chapter_key,
                "word_count": r.word_count,
                "engine": r.engine,
                "snippet": self._snippet(r.full_text or "", lowered_terms),
                "highlighted_terms": terms,
            }
            for r in window
        ]

        return enrich_pagination_aliases(
            {
                "items": items,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total,
            }
        )

    @staticmethod
    def _snippet(
        text_value: str,
        terms: list[str],
        *,
        max_length: int = 240,
        context: int = 60,
    ) -> str:
        if not text_value:
            return ""
        low = text_value.lower()
        idx = min(
            (low.find(t) for t in terms if low.find(t) != -1),
            default=-1,
        )
        if idx == -1:
            snippet = text_value[:max_length]
        else:
            start = max(0, idx - context)
            end = min(len(text_value), idx + max_length - context)
            snippet = text_value[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(text_value):
                snippet = snippet + "..."
        for term in sorted(terms, key=len, reverse=True):
            if term:
                snippet = re.sub(
                    rf"({re.escape(term)})",
                    r"<mark>\1</mark>",
                    snippet,
                    flags=re.IGNORECASE,
                )
        return snippet


def get_ocr_search_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> OcrSearchService:
    followed = FollowedSeriesService(
        db, browse, user_id=ctx.user_id, profile_id=ctx.profile_id
    )
    return OcrSearchService(db, followed)
