"""Full-text search over OCR-extracted chapter text.

Production improvements:
- Case-insensitive LIKE with Unicode collation support
- Multi-word query support (all terms must match)
- Highlighted snippets with <mark> tags around query terms
- Pagination with total count
- Configurable snippet length and context window
- Better snippet extraction centred on the best match location

Scoping
-------

This is a request-facing service only (the OCR pipeline writes ChapterText; it
never searches it), so unlike ``OcrJobService`` it carries the caller's
identity. It has to: the join ChapterText -> Chapter -> Series used to have no
user scoping whatsoever, which made one query a full-text search across every
account's library -- the single widest read in the app, returning series titles,
chapter titles and a snippet of the text itself.

The scoping rule is not defined here. It is ``LibraryService.
scope_readable_series``, i.e. the same two gates the reader applies, so a
transcript can never be reachable through search when the chapter it came from
is not reachable through ``/reader/chapter/{id}``.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database.models import Chapter, ChapterText, Series
from database.session import get_db
from services.library_service import LibraryService, get_library_service


class OcrSearchService:
    """Search service for OCR-extracted text."""

    def __init__(self, db: Session, library: LibraryService | None = None) -> None:
        self._db = db
        # The gate, not a copy of it. Defaults to the unscoped service so a
        # direct ``OcrSearchService(db)`` behaves like every other unscoped
        # caller in the codebase -- restricted to the legacy (NULL-owner)
        # bucket, never exempt from the rule.
        self._library = library if library is not None else LibraryService(db)

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        snippet_length: int = 200,
        context_chars: int = 50,
    ) -> dict[str, Any]:
        """Return chapters whose full_text contains all query terms.

        Args:
            query: Search string. Multiple words are ANDed together.
            limit: Max results per page.
            offset: Number of results to skip (for pagination).
            snippet_length: Maximum length of each snippet.
            context_chars: Characters of context around each match.
        """
        raw = query.strip()
        if not raw:
            from utils.api_pagination import enrich_pagination_aliases

            return enrich_pagination_aliases(
                {"items": [], "total": 0, "offset": offset, "limit": limit}
            )

        # Build AND-filter: each term must appear (case-insensitive)
        terms = [t for t in raw.lower().split() if len(t) >= 2]
        if not terms:
            # Single short word or symbol-only query
            terms = [raw.lower()]

        base_query = self._db.query(ChapterText, Chapter, Series).join(
            Chapter, ChapterText.chapter_id == Chapter.id
        ).join(Series, Chapter.series_id == Series.id)

        for term in terms:
            pattern = f"%{term}%"
            base_query = base_query.filter(
                ChapterText.full_text.ilike(pattern)
            )

        # Scope AFTER the text filter and BEFORE the count: the caller's own
        # ``total`` and ``has_more`` must describe their own result set, or
        # paging walks off the end of a list they were never shown -- and the
        # count alone would still leak how many chapters elsewhere in the
        # household matched the term.
        base_query = self._library.scope_readable_series(base_query)

        total = base_query.count()
        rows = (
            base_query.order_by(ChapterText.word_count.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        results: list[dict[str, Any]] = []
        for chapter_text, chapter, series in rows:
            snippet = self._make_highlighted_snippet(
                chapter_text.full_text or "",
                terms,
                max_length=snippet_length,
                context_chars=context_chars,
            )
            results.append(
                {
                    "chapter_id": chapter.id,
                    "chapter_title": chapter.title,
                    "chapter_number": chapter.number,
                    "series_id": series.id,
                    "series_title": series.title,
                    "word_count": chapter_text.word_count,
                    "engine": chapter_text.engine,
                    "snippet": snippet,
                    "highlighted_terms": terms,
                }
            )

        from utils.api_pagination import enrich_pagination_aliases

        return enrich_pagination_aliases(
            {
                "items": results,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total,
            }
        )

    @staticmethod
    def _make_highlighted_snippet(
        text: str,
        terms: list[str],
        *,
        max_length: int = 200,
        context_chars: int = 50,
    ) -> str:
        """Extract a snippet with <mark> tags around matched terms."""
        if not text or not terms:
            if len(text) <= max_length:
                return text
            return text[:max_length] + "..."

        text_lower = text.lower()

        # Find the best match position (first term with longest match)
        best_idx = -1
        best_term_len = 0
        for term in terms:
            idx = text_lower.find(term)
            if idx != -1 and len(term) > best_term_len:
                best_idx = idx
                best_term_len = len(term)

        if best_idx == -1:
            # No direct match (shouldn't happen with LIKE), return start
            if len(text) <= max_length:
                return text
            return text[:max_length] + "..."

        # Build window around best match
        start = max(0, best_idx - context_chars)
        end = min(len(text), best_idx + best_term_len + context_chars)

        # If the snippet is too short, expand toward the end
        if end - start < max_length:
            remaining = max_length - (end - start)
            end = min(len(text), end + remaining)

        snippet = text[start:end]

        # Add ellipsis
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        # Highlight terms (case-insensitive, preserve original case)
        for term in sorted(terms, key=len, reverse=True):
            snippet = re.sub(
                rf"({re.escape(term)})",
                r"<mark>\1</mark>",
                snippet,
                flags=re.IGNORECASE,
            )

        return snippet


def get_ocr_search_service(
    db: Annotated[Session, Depends(get_db)],
    library: Annotated[LibraryService, Depends(get_library_service)],
) -> OcrSearchService:
    """Build the search service around the request's own gate.

    ``get_library_service`` resolves the (account, profile) from the session and
    the ``X-Profile-Id`` header, so search inherits the identical scoping the
    library and reader routers get -- including the lenient header handling that
    both clients rely on during boot and mid-profile-switch.
    """
    return OcrSearchService(db, library)
