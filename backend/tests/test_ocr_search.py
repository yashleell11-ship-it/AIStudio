"""Tests for OCR full-text search.

Production improvements tested:
- Multi-word AND search
- Highlighted snippets with <mark> tags
- Pagination with total count and has_more
"""

from __future__ import annotations

from database.models import Chapter, ChapterText, Library, Series, UserSeriesState
from services.ocr_search import OcrSearchService


class TestOcrSearchService:
    def _seed(self, db_session):
        lib = Library(name="Test", root_path="/tmp/test")
        db_session.add(lib)
        db_session.flush()
        series = Series(
            library_id=lib.id, title="Test Series", folder_path="/tmp/test/s"
        )
        db_session.add(series)
        db_session.flush()
        chapter = Chapter(
            series_id=series.id,
            title="Ch1",
            number=1,
            folder_path="/tmp/test/s/c1",
        )
        db_session.add(chapter)
        # OCR search is scoped to series the caller may read, exactly like the
        # reader -- a transcript must not be findable when the chapter it came
        # from is not. These tests drive the unscoped service, so the claim goes
        # in the legacy (NULL-owner) bucket that caller is restricted to.
        db_session.add(
            UserSeriesState(
                user_id=None,
                profile_id=None,
                series_id=series.id,
                in_library=True,
            )
        )
        db_session.flush()
        return series, chapter

    def test_search_found(self, db_session) -> None:
        series, chapter = self._seed(db_session)
        ct = ChapterText(
            chapter_id=chapter.id,
            full_text="The quick brown fox jumps over the lazy dog.",
            word_count=9,
        )
        db_session.add(ct)
        db_session.commit()

        service = OcrSearchService(db_session)
        result = service.search("fox")

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["chapter_id"] == chapter.id
        assert result["items"][0]["series_title"] == "Test Series"
        assert "<mark>" in result["items"][0]["snippet"].lower()

    def test_multi_word_and_search(self, db_session) -> None:
        """Multi-word queries require ALL terms to match."""
        series, chapter = self._seed(db_session)
        ct1 = ChapterText(
            chapter_id=chapter.id,
            full_text="The quick brown fox jumps over the lazy dog.",
            word_count=9,
        )
        db_session.add(ct1)
        db_session.commit()

        service = OcrSearchService(db_session)
        # Both terms present → match
        result = service.search("fox dog")
        assert result["total"] == 1

        # One term missing → no match
        result2 = service.search("fox elephant")
        assert result2["total"] == 0

    def test_pagination(self, db_session) -> None:
        series, chapter = self._seed(db_session)
        for i in range(5):
            c = Chapter(
                series_id=series.id,
                title=f"Ch{i}",
                number=i,
                folder_path=f"/tmp/test/s/c{i+2}",
            )
            db_session.add(c)
            db_session.flush()
            ct = ChapterText(
                chapter_id=c.id,
                full_text="The quick brown fox jumps over the lazy dog.",
                word_count=9,
            )
            db_session.add(ct)
        db_session.commit()

        service = OcrSearchService(db_session)
        result = service.search("fox", limit=2, offset=0)
        assert result["total"] == 5
        assert len(result["items"]) == 2
        assert result["has_more"] is True

        result2 = service.search("fox", limit=2, offset=2)
        assert len(result2["items"]) == 2
        assert result2["has_more"] is True

        result3 = service.search("fox", limit=2, offset=4)
        assert len(result3["items"]) == 1
        assert result3["has_more"] is False

    def test_highlighted_snippet(self, db_session) -> None:
        series, chapter = self._seed(db_session)
        ct = ChapterText(
            chapter_id=chapter.id,
            full_text="The quick brown FOX jumps over the lazy dog.",
            word_count=9,
        )
        db_session.add(ct)
        db_session.commit()

        service = OcrSearchService(db_session)
        result = service.search("fox")
        snippet = result["items"][0]["snippet"]
        # Should preserve original case and wrap in <mark>
        assert "<mark>FOX</mark>" in snippet or "<mark>fox</mark>" in snippet.lower()

    def test_empty_query(self, db_session) -> None:
        service = OcrSearchService(db_session)
        result = service.search("")
        assert result["items"] == []
        assert result["total"] == 0

    def test_search_not_found(self, db_session) -> None:
        series, chapter = self._seed(db_session)
        ct = ChapterText(
            chapter_id=chapter.id,
            full_text="The quick brown fox jumps over the lazy dog.",
            word_count=9,
        )
        db_session.add(ct)
        db_session.commit()

        service = OcrSearchService(db_session)
        result = service.search("missing")
        assert result["total"] == 0
        assert result["items"] == []
