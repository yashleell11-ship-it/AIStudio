"""Client-driven OCR ingest (spec §3.9, §4.4).

The phone/browser runs OCR on downloaded pages and uploads the text here.
``chapter_ocr`` is **global** — one row per ``(source_id, series_key,
chapter_key)``, not per user: the OCR text of a chapter is a property of the
chapter (same rationale as ``source_health``). Disclosure is prevented at
search time by filtering results to the caller's followed series + 18+ gate.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.profile_context import ProfileContext, resolve_profile_context
from core.time_utils import utcnow
from database.models import ChapterOcr
from database.session import get_db


def _word_count(text: str) -> int:
    return len(text.split())


class OcrIngestService:
    def __init__(self, db: Session, *, user_id: int | None = None) -> None:
        self._db = db
        self._user_id = user_id

    def ingest_chapter(
        self,
        *,
        source_id: str,
        series_key: str,
        chapter_key: str,
        pages: list[dict[str, Any]],
        language: str | None = None,
        engine: str = "unknown",
        chapter_number: float | None = None,  # noqa: ARG002 - accepted, not stored
    ) -> dict[str, Any]:
        """Upsert one chapter's OCR text. Rebuilds ``full_text`` from pages.

        An upload for an existing key **replaces** (last engine wins) unless the
        incoming ``word_count`` is 0 (spec §3.9).
        """
        series_key = fully_unquote(series_key)
        chapter_key = fully_unquote(chapter_key)

        normalized_pages = [
            {
                "page": int(p.get("page", i + 1)),
                "text": str(p.get("text") or ""),
                "boxes": p.get("boxes"),
            }
            for i, p in enumerate(pages)
        ]
        full_text = "\n".join(p["text"] for p in normalized_pages if p["text"]).strip()
        wc = _word_count(full_text)

        row = self._db.execute(
            select(ChapterOcr).where(
                ChapterOcr.source_id == source_id,
                ChapterOcr.series_key == series_key,
                ChapterOcr.chapter_key == chapter_key,
            )
        ).scalar_one_or_none()

        if row is not None and wc == 0:
            # Never overwrite a good transcript with an empty one.
            return self._serialize(row)

        if row is None:
            row = ChapterOcr(
                source_id=source_id,
                series_key=series_key,
                chapter_key=chapter_key,
            )
            self._db.add(row)

        row.full_text = full_text or None
        row.page_texts = json.dumps(normalized_pages)
        row.language = language or row.language
        row.engine = engine or "unknown"
        row.word_count = wc
        row.contributed_by_user_id = self._user_id
        row.updated_at = utcnow()
        self._db.commit()
        self._db.refresh(row)
        return self._serialize(row)

    def get_chapter(
        self, source_id: str, series_key: str, chapter_key: str
    ) -> dict[str, Any] | None:
        row = self._db.execute(
            select(ChapterOcr).where(
                ChapterOcr.source_id == source_id,
                ChapterOcr.series_key == fully_unquote(series_key),
                ChapterOcr.chapter_key == fully_unquote(chapter_key),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        payload = self._serialize(row)
        payload["page_texts"] = json.loads(row.page_texts) if row.page_texts else []
        return payload

    def coverage(self, source_id: str, series_key: str) -> dict[str, Any]:
        """Which chapters of a series already have OCR (so the client only
        OCRs the gaps)."""
        series_key = fully_unquote(series_key)
        rows = self._db.execute(
            select(ChapterOcr.chapter_key, ChapterOcr.word_count).where(
                ChapterOcr.source_id == source_id,
                ChapterOcr.series_key == series_key,
            )
        ).all()
        return {
            "source_id": source_id,
            "series_key": series_key,
            "chapters": [
                {"chapter_key": k, "word_count": wc} for k, wc in rows
            ],
        }

    @staticmethod
    def _serialize(row: ChapterOcr) -> dict[str, Any]:
        return {
            "source_id": row.source_id,
            "series_key": row.series_key,
            "chapter_key": row.chapter_key,
            "language": row.language,
            "engine": row.engine,
            "word_count": row.word_count,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


def get_ocr_ingest_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> OcrIngestService:
    # chapter_ocr is a global table; user id is audit-only (contributed_by).
    return OcrIngestService(db, user_id=ctx.user_id)
