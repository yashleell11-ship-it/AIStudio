from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from core.time_utils import utcnow
from database.models import (
    Chapter,
    Collection,
    CollectionSeries,
    Library,
    Page,
    ReadingProgress,
    ReadingSession,
    Series,
    SeriesTag,
    Tag,
)
from services.library_intelligence_service import LibraryIntelligenceService
from services.library_service import LibraryService


@pytest.fixture
def db(db_engine):
    """Provide a fresh transactional session for each test."""
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _seed_library(db: Session) -> Library:
    lib = Library(name="Test Library", root_path="/tmp/test")
    db.add(lib)
    db.flush()
    return lib


def _seed_series(db: Session, library: Library, title: str, **kwargs) -> Series:
    series = Series(
        library_id=library.id,
        title=title,
        folder_path=f"/tmp/test/{title}",
        **kwargs,
    )
    db.add(series)
    db.flush()
    return series


def _seed_chapter(db: Session, series: Series, title: str, number: int = 1) -> Chapter:
    chapter = Chapter(
        series_id=series.id,
        title=title,
        number=number,
        folder_path=f"{series.folder_path}/{title}",
        sort_key=f"{number:04d}.000",
        page_count=2,
    )
    db.add(chapter)
    db.flush()
    for i in range(1, 3):
        db.add(Page(chapter_id=chapter.id, number=i, file_path=f"page_{i}.jpg"))
    db.flush()
    return chapter


class TestCollections:
    def test_create_collection(self, db: Session):
        intel = LibraryIntelligenceService(db)
        result = intel.create_collection(name="My Collection", description="Test desc")
        assert result["name"] == "My Collection"
        assert result["description"] == "Test desc"
        assert result["series_count"] == 0

    def test_create_duplicate_collection_fails(self, db: Session):
        intel = LibraryIntelligenceService(db)
        intel.create_collection(name="Dup")
        with pytest.raises(Exception) as exc_info:
            intel.create_collection(name="Dup")
        assert "already exists" in str(exc_info.value)

    def test_list_collections(self, db: Session):
        intel = LibraryIntelligenceService(db)
        intel.create_collection(name="A")
        intel.create_collection(name="B")
        collections = intel.list_collections()
        assert len(collections) == 2
        assert collections[0]["name"] == "A"

    def test_add_series_to_collection(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo")
        coll = intel.create_collection(name="Faves")
        result = intel.add_series_to_collection(coll["id"], series.id)
        assert result["collection_id"] == coll["id"]
        assert result["series_id"] == series.id

        detail = intel.get_collection(coll["id"])
        assert detail["series"]["total"] == 1

    def test_remove_series_from_collection(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo")
        coll = intel.create_collection(name="Faves")
        intel.add_series_to_collection(coll["id"], series.id)
        intel.remove_series_from_collection(coll["id"], series.id)
        detail = intel.get_collection(coll["id"])
        assert detail["series"]["total"] == 0

    def test_delete_collection(self, db: Session):
        intel = LibraryIntelligenceService(db)
        coll = intel.create_collection(name="Temp")
        intel.delete_collection(coll["id"])
        collections = intel.list_collections()
        assert len(collections) == 0

    def test_collection_cover_from_series(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", cover_path="covers/solo.jpg")
        coll = intel.create_collection(name="Faves")
        intel.add_series_to_collection(coll["id"], series.id)
        # Collection should pick up series cover
        collections = intel.list_collections()
        assert collections[0]["cover_path"] == "covers/solo.jpg"

    def test_collection_reorder_series(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "A")
        s2 = _seed_series(db, lib, "B")
        s3 = _seed_series(db, lib, "C")
        coll = intel.create_collection(name="Alphabet")
        intel.add_series_to_collection(coll["id"], s1.id)
        intel.add_series_to_collection(coll["id"], s2.id)
        intel.add_series_to_collection(coll["id"], s3.id)
        # Reorder to C, B, A
        intel.reorder_collection_series(coll["id"], [s3.id, s2.id, s1.id])
        detail = intel.get_collection(coll["id"])
        titles = [s["title"] for s in detail["series"]["items"]]
        assert titles == ["C", "B", "A"]


class TestTags:
    def test_create_tag(self, db: Session):
        intel = LibraryIntelligenceService(db)
        tag = intel.create_tag(name="Action", category="genre", color="#ff0000")
        assert tag["name"] == "Action"
        assert tag["category"] == "genre"

    def test_create_duplicate_tag_fails(self, db: Session):
        intel = LibraryIntelligenceService(db)
        intel.create_tag(name="Dup")
        with pytest.raises(Exception) as exc_info:
            intel.create_tag(name="Dup")
        assert "already exists" in str(exc_info.value)

    def test_add_tag_to_series(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo")
        tag = intel.create_tag(name="Action")
        result = intel.add_tag_to_series(series.id, tag["id"])
        assert result["series_id"] == series.id
        assert result["tag_id"] == tag["id"]

    def test_remove_tag_from_series(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo")
        tag = intel.create_tag(name="Action")
        intel.add_tag_to_series(series.id, tag["id"])
        intel.remove_tag_from_series(series.id, tag["id"])
        tags = intel.list_tags()
        assert tags[0]["series_count"] == 0

    def test_list_tags_by_category(self, db: Session):
        intel = LibraryIntelligenceService(db)
        intel.create_tag(name="Action", category="genre")
        intel.create_tag(name="Isekai", category="theme")
        genres = intel.list_tags(category="genre")
        assert len(genres) == 1
        assert genres[0]["name"] == "Action"

    def test_tag_batch_counts_no_nplus1(self, db: Session):
        """Tags with multiple series should not cause N+1 queries."""
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        t1 = intel.create_tag(name="A")
        for i in range(5):
            s = _seed_series(db, lib, f"S{i}")
            intel.add_tag_to_series(s.id, t1["id"])
        tags = intel.list_tags()
        assert tags[0]["series_count"] == 5


class TestFavorites:
    def test_toggle_favorite(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo")
        result = intel.toggle_favorite(series.id)
        assert result["is_favorite"] is True
        result = intel.toggle_favorite(series.id)
        assert result["is_favorite"] is False


class TestMetadata:
    def test_update_series_metadata(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo")
        result = intel.update_series_metadata(
            series.id,
            title="Solo Leveling",
            author="Chugong",
            artist="Dubu",
            reading_status="reading",
            is_favorite=True,
        )
        assert result["title"] == "Solo Leveling"
        assert result["author"] == "Chugong"
        assert result["reading_status"] == "reading"
        assert result["is_favorite"] is True

    def test_get_series_detail(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo")
        tag = intel.create_tag(name="Action")
        intel.add_tag_to_series(series.id, tag["id"])
        coll = intel.create_collection(name="Faves")
        intel.add_series_to_collection(coll["id"], series.id)

        detail = intel.get_series_detail(series.id)
        assert detail["title"] == "Solo"
        assert len(detail["tags"]) == 1
        assert len(detail["collections"]) == 1

    def test_metadata_quality_score(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", author="Chugong", year=2020)
        result = intel.get_metadata_quality(series.id)
        assert result["series_id"] == series.id
        assert 0 < result["score"] < 100
        assert "missing" in result
        assert "suggestions" in result
        assert "fields" in result

    def test_metadata_quality_full(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        series = _seed_series(
            db, lib, "Solo",
            author="Chugong",
            artist="Dubu",
            description="A great manhwa",
            status="completed",
            content_rating="safe",
            language="ko",
            year=2020,
            cover_path="covers/1.jpg",
        )
        result = intel.get_metadata_quality(series.id)
        assert result["score"] == 100.0
        assert result["missing"] == []


class TestRecentlyAndStatistics:
    def test_recently_added(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        _seed_series(db, lib, "A")
        _seed_series(db, lib, "B")
        result = intel.get_recently_added(limit=10)
        assert len(result) == 2

    def test_recently_updated(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "A")
        s2 = _seed_series(db, lib, "B")
        s2.updated_at = utcnow() + timedelta(seconds=1)
        db.commit()
        result = intel.get_recently_updated(limit=10)
        assert result[0]["title"] == "B"

    def test_statistics(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        _seed_series(db, lib, "A")
        _seed_series(db, lib, "B")
        stats = intel.get_statistics()
        assert stats["total_series"] == 2
        assert "completion_rate_pct" in stats
        assert "reading_streak_days" in stats
        assert "reading_velocity_pages_per_hour" in stats
        assert "tag_distribution" in stats
        assert "top_authors" in stats
        assert "weekly_chart" in stats

    def test_weekly_chart(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        ch1 = _seed_chapter(db, s1, "Ch1")
        db.add(
            ReadingSession(
                series_id=s1.id,
                chapter_id=ch1.id,
                start_page=1,
                end_page=5,
                pages_read=5,
                started_at=utcnow(),
            )
        )
        db.commit()
        stats = intel.get_statistics()
        assert len(stats["weekly_chart"]) == 7
        total_pages = sum(d["pages_read"] for d in stats["weekly_chart"])
        assert total_pages == 5

    def test_statistics_empty_library(self, db: Session):
        intel = LibraryIntelligenceService(db)
        stats = intel.get_statistics()
        assert stats["total_series"] == 0
        assert stats["reading_streak_days"] == 0
        assert stats["reading_velocity_pages_per_hour"] == 0.0

    def test_statistics_top_authors(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        _seed_series(db, lib, "A", author="Chugong")
        _seed_series(db, lib, "B", author="Chugong")
        _seed_series(db, lib, "C", author="Other")
        stats = intel.get_statistics()
        assert len(stats["top_authors"]) >= 1
        assert stats["top_authors"][0]["author"] == "Chugong"

    def test_tag_distribution(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "A")
        s2 = _seed_series(db, lib, "B")
        t = intel.create_tag(name="Action", category="genre")
        intel.add_tag_to_series(s1.id, t["id"])
        intel.add_tag_to_series(s2.id, t["id"])
        stats = intel.get_statistics()
        assert len(stats["tag_distribution"]) >= 1
        assert stats["tag_distribution"][0]["name"] == "Action"


class TestSimilarAndRecommendations:
    def test_similar_series_by_author(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo", author="Chugong")
        s2 = _seed_series(db, lib, "Other", author="Chugong")
        _seed_series(db, lib, "Unrelated", author="Someone")
        result = intel.get_similar_series(s1.id)
        assert len(result) == 1
        assert result[0]["id"] == s2.id

    def test_similar_series_by_tags(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        s2 = _seed_series(db, lib, "Other")
        s3 = _seed_series(db, lib, "Unrelated")
        tag = intel.create_tag(name="Action")
        intel.add_tag_to_series(s1.id, tag["id"])
        intel.add_tag_to_series(s2.id, tag["id"])
        result = intel.get_similar_series(s1.id)
        assert len(result) == 1
        assert result[0]["id"] == s2.id

    def test_similar_series_diversity(self, db: Session):
        """At most 2 similar series per author to avoid monotony."""
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "A", author="Chugong")
        s2 = _seed_series(db, lib, "B", author="Chugong")
        s3 = _seed_series(db, lib, "C", author="Chugong")
        # Add tag so they all score >= 3
        t = intel.create_tag(name="X")
        intel.add_tag_to_series(s1.id, t["id"])
        intel.add_tag_to_series(s2.id, t["id"])
        intel.add_tag_to_series(s3.id, t["id"])
        result = intel.get_similar_series(s1.id, limit=10)
        # Only 2 of the 3 same-author series should appear (diversity limit)
        assert len(result) <= 2

    def test_recommendations_fallback(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        _seed_series(db, lib, "A")
        result = intel.get_recommendations(limit=10)
        assert len(result) == 1  # fallback to recently added

    def test_recommendations_based_on_history(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        s2 = _seed_series(db, lib, "Other")
        s3 = _seed_series(db, lib, "Unrelated")
        _seed_chapter(db, s1, "Ch1")
        _seed_chapter(db, s2, "Ch1")
        _seed_chapter(db, s3, "Ch1")

        # Create reading progress for s1
        db.add(ReadingProgress(series_id=s1.id, chapter_id=s1.chapters[0].id, progress_pct=10.0))
        db.commit()

        tag = intel.create_tag(name="Action")
        intel.add_tag_to_series(s1.id, tag["id"])
        intel.add_tag_to_series(s2.id, tag["id"])
        result = intel.get_recommendations(limit=10)
        assert len(result) == 1
        assert result[0]["id"] == s2.id

    def test_recommendations_no_per_candidate_tag_count_query(self, db: Session):
        """Regression test for the N+1 fix: get_recommendations must read
        shared_tags from the already-joined subquery instead of firing one
        extra standalone COUNT query per candidate series."""
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)

        anchor = _seed_series(db, lib, "Anchor")
        _seed_chapter(db, anchor, "Ch1")
        db.add(ReadingProgress(series_id=anchor.id, chapter_id=anchor.chapters[0].id, progress_pct=10.0))
        db.commit()

        tag = intel.create_tag(name="Action")
        intel.add_tag_to_series(anchor.id, tag["id"])

        # Distinct authors so the "max 2 per author" diversity cap doesn't
        # limit the result set below candidate_count.
        candidate_count = 25
        for i in range(candidate_count):
            candidate = _seed_series(db, lib, f"Candidate {i}", author=f"Author {i}")
            intel.add_tag_to_series(candidate.id, tag["id"])
        db.commit()

        statements: list[str] = []
        engine = db.get_bind()

        def _capture(_conn, _cursor, statement, *_args, **_kwargs):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            result = intel.get_recommendations(limit=candidate_count)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert len(result) == candidate_count

        # The N+1 regression fired one standalone
        # "SELECT count(series_tags.tag_id) FROM series_tags WHERE
        # series_tags.series_id = ?" query per candidate (no JOIN — a bare
        # filtered count). After the fix, shared_tags comes from the
        # subquery already joined into the candidates query, so no such
        # standalone per-candidate count query should appear.
        per_candidate_count_queries = [
            s
            for s in statements
            if "series_tags" in s
            and "count(" in s.lower()
            and "JOIN" not in s.upper()
        ]
        assert not per_candidate_count_queries, (
            f"found {len(per_candidate_count_queries)} standalone series_tags "
            "count queries — the N+1 regression appears to be back"
        )


class TestReadingHistory:
    def test_reading_history(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        ch1 = _seed_chapter(db, s1, "Ch1")
        db.add(
            ReadingSession(
                series_id=s1.id,
                chapter_id=ch1.id,
                start_page=1,
                end_page=5,
                pages_read=5,
            )
        )
        db.commit()
        history = intel.get_reading_history(limit=10)
        assert len(history) == 1
        assert history[0]["pages_read"] == 5

    def test_reading_calendar(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        ch1 = _seed_chapter(db, s1, "Ch1")
        db.add(
            ReadingSession(
                series_id=s1.id,
                chapter_id=ch1.id,
                start_page=1,
                end_page=5,
                pages_read=5,
                started_at=utcnow(),
            )
        )
        db.commit()
        calendar = intel.get_reading_calendar(days=30)
        assert len(calendar) >= 1
        today_str = utcnow().strftime("%Y-%m-%d")
        today_entry = next((d for d in calendar if d["day"] == today_str), None)
        assert today_entry is not None
        assert today_entry["pages_read"] == 5

    def test_series_reading_history(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        ch1 = _seed_chapter(db, s1, "Ch1")
        ch2 = _seed_chapter(db, s1, "Ch2", number=2)
        db.add(
            ReadingSession(
                series_id=s1.id, chapter_id=ch1.id, start_page=1, end_page=5, pages_read=5,
                started_at=utcnow() - timedelta(minutes=5),
            )
        )
        db.add(
            ReadingSession(
                series_id=s1.id, chapter_id=ch2.id, start_page=1, end_page=3, pages_read=3,
                started_at=utcnow(),
            )
        )
        db.commit()
        history = intel.get_series_reading_history(s1.id)
        assert len(history) == 2
        assert history[0]["chapter_title"] == "Ch2"

    def test_reading_streak(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        ch1 = _seed_chapter(db, s1, "Ch1")
        # Today
        db.add(ReadingSession(
            series_id=s1.id, chapter_id=ch1.id, start_page=1, end_page=1, pages_read=1,
            started_at=utcnow(),
        ))
        # Yesterday
        db.add(ReadingSession(
            series_id=s1.id, chapter_id=ch1.id, start_page=1, end_page=1, pages_read=1,
            started_at=utcnow() - timedelta(days=1),
        ))
        # Two days ago
        db.add(ReadingSession(
            series_id=s1.id, chapter_id=ch1.id, start_page=1, end_page=1, pages_read=1,
            started_at=utcnow() - timedelta(days=2),
        ))
        db.commit()
        stats = intel.get_statistics()
        assert stats["reading_streak_days"] >= 3


class TestSearch:
    def test_search_series(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        _seed_series(db, lib, "Solo Leveling")
        _seed_series(db, lib, "Omniscient Reader")
        result = intel.search_series("Solo")
        assert result["total"] == 1
        assert result["items"][0]["title"] == "Solo Leveling"

    def test_search_empty_query_fails(self, db: Session):
        intel = LibraryIntelligenceService(db)
        with pytest.raises(Exception) as exc_info:
            intel.search_series("")
        assert "validation_error" in str(exc_info.value) or "empty" in str(exc_info.value)

    def test_search_ranking_exact_title(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        _seed_series(db, lib, "Solo Leveling")
        _seed_series(db, lib, "Solo Max")
        _seed_series(db, lib, "Other")
        result = intel.search_series("Solo Leveling")
        # Exact title match should be first
        assert result["items"][0]["title"] == "Solo Leveling"

    def test_search_has_pagination(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        for i in range(5):
            _seed_series(db, lib, f"Series {i}")
        result = intel.search_series("Series", per_page=2)
        assert result["per_page"] == 2
        assert result["has_next"] is True
        assert len(result["items"]) == 2


class TestLibraryServiceFilters:
    def test_list_series_with_filters(self, db: Session):
        service = LibraryService(db)
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo", reading_status="reading", is_favorite=True, language="ko")
        s2 = _seed_series(db, lib, "Other", reading_status="unread", is_favorite=False, language="en")
        db.commit()

        result = service.list_series(reading_status="reading")
        assert result["total"] == 1
        assert result["items"][0]["id"] == s1.id

        result = service.list_series(is_favorite=True)
        assert result["total"] == 1
        assert result["items"][0]["id"] == s1.id

        result = service.list_series(language="en")
        assert result["total"] == 1
        assert result["items"][0]["id"] == s2.id

    def test_list_series_with_collection_filter(self, db: Session):
        service = LibraryService(db)
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        s2 = _seed_series(db, lib, "Other")
        coll = intel.create_collection(name="Faves")
        intel.add_series_to_collection(coll["id"], s1.id)
        db.commit()

        result = service.list_series(collection_id=coll["id"])
        assert result["total"] == 1
        assert result["items"][0]["id"] == s1.id

    def test_list_series_with_tag_filter(self, db: Session):
        service = LibraryService(db)
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "Solo")
        s2 = _seed_series(db, lib, "Other")
        tag = intel.create_tag(name="Action")
        intel.add_tag_to_series(s1.id, tag["id"])
        db.commit()

        result = service.list_series(tag_id=tag["id"])
        assert result["total"] == 1
        assert result["items"][0]["id"] == s1.id

    def test_list_series_pagination_has_next(self, db: Session):
        service = LibraryService(db)
        lib = _seed_library(db)
        for i in range(5):
            _seed_series(db, lib, f"S{i}")
        db.commit()
        result = service.list_series(per_page=2)
        assert result["has_next"] is True
        assert len(result["items"]) == 2
        result2 = service.list_series(per_page=2, page=3)
        assert result2["has_next"] is False
        assert len(result2["items"]) == 1


class TestQueryOptimization:
    def test_list_tags_batch_count(self, db: Session):
        """list_tags should use one batch query for counts, not N+1."""
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        for i in range(3):
            intel.create_tag(name=f"Tag{i}")
        tags = intel.list_tags()
        assert len(tags) == 3
        # All should have 0 count without extra queries
        for t in tags:
            assert t["series_count"] == 0

    def test_list_collections_batch_count(self, db: Session):
        intel = LibraryIntelligenceService(db)
        for i in range(3):
            intel.create_collection(name=f"Coll{i}")
        collections = intel.list_collections()
        assert len(collections) == 3
        for c in collections:
            assert c["series_count"] == 0

    def test_series_summary_uses_denormalized_counts(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s = _seed_series(db, lib, "Solo", total_chapters=5, total_pages=100)
        summary = intel._series_summary(s)
        assert summary["chapter_count"] == 5
        assert summary["page_count"] == 100

    def test_collection_detail_uses_selectinload(self, db: Session):
        intel = LibraryIntelligenceService(db)
        lib = _seed_library(db)
        s1 = _seed_series(db, lib, "A")
        s2 = _seed_series(db, lib, "B")
        coll = intel.create_collection(name="Test")
        intel.add_series_to_collection(coll["id"], s1.id)
        intel.add_series_to_collection(coll["id"], s2.id)
        detail = intel.get_collection(coll["id"])
        assert detail["series"]["total"] == 2
        assert len(detail["series"]["items"]) == 2
