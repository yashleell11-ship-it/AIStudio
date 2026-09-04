"""Client-driven OCR ingest (spec §3.9, §4.4).

The phone/browser runs OCR on downloaded pages and uploads the text here.
``chapter_ocr`` is **global** — one row per ``(source_id, series_key,
chapter_key)``, not per user: the OCR text of a chapter is a property of the
chapter (same rationale as ``source_health``). The write stays global; every
path that *returns* stored text is scoped to the caller's followed series +
18+ gate, which is the whole reason spec §3.9 calls the global row "no
disclosure risk". ``ocr_search`` enforced that; ``get_chapter`` and
``coverage`` did not, and handed any account the transcript of any chapter on
any source — mature sources included.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.connector_directory import descriptor_for_source
from core.content_rating import (
    TRACKER_RATING_MATURE,
    resolve_mature_gate,
    resolve_tracker_rating,
)
from core.profile_context import ProfileContext, resolve_profile_context
from core.time_utils import utcnow
from database.models import ChapterOcr, FollowedSeries
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service


def _word_count(text: str) -> int:
    return len(text.split())


class OcrIngestService:
    def __init__(
        self,
        db: Session,
        browse: BrowseService,
        *,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        """``browse`` is required, not optional, so no caller can build a
        service whose reads are ungated — that was the shape of the bug."""
        self._db = db
        self._browse = browse
        self._user_id = user_id
        self._profile_id = profile_id
        # Resolved once per request: the gate is a property of the (user,
        # profile) pair and cannot change mid-request.
        self._gate_cache: bool | None = None

    # --- read scope ----------------------------------------------------

    def _gate_open(self) -> bool:
        """This caller's own 18+ gate.

        Resolved from the (user, profile) via ``resolve_mature_gate`` — the
        single resolution path. Reading ``get_settings().mature_content_enabled``
        here instead is what once made the in-app toggle inert.
        """
        if self._gate_cache is None:
            self._gate_cache = resolve_mature_gate(
                self._db, self._profile_id, self._user_id
            )
        return self._gate_cache

    def _may_read(self, source_id: str, series_key: str) -> bool:
        """Whether this ``(user_id, profile_id)`` may be shown OCR for a series.

        Two gates, both per-(user, profile), matching the two the rest of the
        read surface applies:

        * the *source* gate — ``ensure_visible`` is what every other read of a
          global table runs first (browse cache, cover cache, reader), so a
          mature source stays 404 here exactly as it is everywhere else. It
          raises rather than returning False, so the response is byte-identical
          to the one browse gives for that source.
        * the *follow* scope — ``chapter_ocr`` rows are global, so the only
          thing standing between one profile and another's contribution is
          "does this profile follow the series". ``series_key`` must already be
          unquoted: follows store it that way.

        A followed row is still hidden when the profile's gate is closed and
        the row resolves mature (``mature_override`` / captured
        ``content_rating``) — the source gate alone misses an 18+ series on a
        general source.
        """
        self._browse.ensure_visible(source_id)
        if self._user_id is None or self._profile_id is None:
            # ``followed_series.profile_id`` is NOT NULL, so an unscoped caller
            # has no library to match against; denial is the same answer a
            # lookup would give, reached without one.
            return False
        row = self._db.execute(
            select(FollowedSeries).where(
                FollowedSeries.user_id == self._user_id,
                FollowedSeries.profile_id == self._profile_id,
                FollowedSeries.source_id == source_id,
                FollowedSeries.series_key == series_key,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        if self._gate_open():
            return True
        return (
            resolve_tracker_rating(row, descriptor_for_source(source_id))
            != TRACKER_RATING_MATURE
        )

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
        """One chapter's stored transcript, or ``None``.

        A series this profile may not see returns ``None`` exactly as an
        un-OCR'd chapter does, and the route turns both into the same 404 --
        off-limits is indistinguishable from absent. (A gated *source* 404s one
        step earlier, inside ``_may_read``, with the same body browse gives.)
        """
        series_key = fully_unquote(series_key)
        if not self._may_read(source_id, series_key):
            return None
        row = self._db.execute(
            select(ChapterOcr).where(
                ChapterOcr.source_id == source_id,
                ChapterOcr.series_key == series_key,
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
        if not self._may_read(source_id, series_key):
            # The empty listing, not an error: same reasoning as get_chapter --
            # "you may not see this" reads as "nothing here yet". A gated
            # source never reaches here; ``_may_read`` raises browse's 404.
            return {"source_id": source_id, "series_key": series_key, "chapters": []}
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
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> OcrIngestService:
    # chapter_ocr is a global table: on write the user id is audit-only
    # (contributed_by), on read (user_id, profile_id) is the scope. ``browse``
    # already carries this caller's resolved 18+ gate.
    return OcrIngestService(
        db, browse, user_id=ctx.user_id, profile_id=ctx.profile_id
    )
