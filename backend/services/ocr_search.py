"""Full-text search over OCR-extracted chapter text.

Production improvements:
- Case-insensitive LIKE with Unicode collation support
- Multi-word query support (all terms must match)
- Highlighted snippets with <mark> tags around query terms
- Pagination with total count
- Configurable snippet length and context window
- Better snippet extraction centred on the best match location
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database.models import Chapter, ChapterText, Series


class OcrSearchService:
    """Search service for OCR-extracted text."""

    def __init__(self, db: Session) -> None:
        self._db = db

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
