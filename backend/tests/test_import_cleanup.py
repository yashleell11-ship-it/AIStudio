from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from database.models import Chapter, Library, Page, Series
from services.import_cleanup import (
    ImportCleanupService,
    is_direct_child_path,
)
from utils.scanner import _extract_chapter_number


# ------------------------------------------------------------------
# Chapter number parsing (regression tests for decimal support)
# ------------------------------------------------------------------


def test_extract_chapter_number_supports_decimals():
    """Decimal chapter numbers like 13.5 must not be truncated."""
    assert _extract_chapter_number("Chapter 13.5") == 13.5
    assert _extract_chapter_number("120.1 - Omake") == 120.1
    assert _extract_chapter_number("Episode 0.5") == 0.5


def test_extract_chapter_number_integer_chapters_still_work():
    """Integer chapter numbers must continue to parse correctly."""
    assert _extract_chapter_number("Chapter 42") == 42.0
    assert _extract_chapter_number("Episode 0") == 0.0
    assert _extract_chapter_number("Vol 1 Ch 99") == 1.0


def test_extract_chapter_number_returns_none_for_no_digits():
    """Names without digits should return None."""
    assert _extract_chapter_number("Omake") is None
    assert _extract_chapter_number("") is None


def test_is_direct_child_path(tmp_path: Path):
    parent = tmp_path / "Solo Leveling"
    child = parent / "Episode 1"
    parent.mkdir()
    child.mkdir()
    assert is_direct_child_path(str(child.resolve()), str(parent.resolve()))
    assert not is_direct_child_path(str(parent.resolve()), str(parent.resolve()))


def test_global_merge_removes_four_orphan_episodes(db_session, tmp_path: Path):
    series_dir = tmp_path / "Solo Leveling"
    for episode in ["Episode 0", "Episode 1", "Episode 2", "Episode 3"]:
        chapter_dir = series_dir / episode
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "001.jpg").write_bytes(b"page")

    from database.models import Chapter, Library, Page, Series

    library = Library(
        name=series_dir.name,
        root_path=str(series_dir.resolve()),
    )
    db_session.add(library)
    db_session.flush()

    parent = Series(
        library_id=library.id,
        title="Solo Leveling",
        folder_path=str(series_dir.resolve()),
    )
    db_session.add(parent)
    db_session.flush()

    for episode in ["Episode 0", "Episode 1", "Episode 2", "Episode 3"]:
        episode_path = series_dir / episode
        orphan = Series(
            library_id=library.id,
            title=episode,
            folder_path=str(episode_path.resolve()),
        )
        db_session.add(orphan)
        db_session.flush()
        chapter = Chapter(
            series_id=orphan.id,
            title="Chapter 1",
            number=1,
            folder_path=str(episode_path.resolve()),
            page_count=1,
        )
        db_session.add(chapter)
        db_session.flush()
        db_session.add(
            Page(
                chapter_id=chapter.id,
                number=1,
                file_path=str(episode_path / "001.jpg"),
            )
        )

    db_session.commit()

    removed = ImportCleanupService(db_session).merge_all_orphans_global()
    db_session.commit()

    assert removed == 4
    remaining = db_session.query(Series).all()
    assert len(remaining) == 1
    assert remaining[0].title == "Solo Leveling"
    chapters = (
        db_session.query(Chapter)
        .filter(Chapter.series_id == remaining[0].id)
        .order_by(Chapter.number.asc().nullslast(), Chapter.id.asc())
        .all()
    )
    assert len(chapters) == 4
    assert [chapter.title for chapter in chapters] == [
        "Episode 0",
        "Episode 1",
        "Episode 2",
        "Episode 3",
    ]


def test_merge_preserves_decimal_chapter_numbers(db_session, tmp_path: Path):
    """When an orphan series is merged, its decimal chapter number must be preserved."""
    series_dir = tmp_path / "Solo Leveling"
    episode_dir = series_dir / "Episode 13.5"
    episode_dir.mkdir(parents=True)
    (episode_dir / "001.jpg").write_bytes(b"page")

    library = Library(
        name=series_dir.name,
        root_path=str(series_dir.resolve()),
    )
    db_session.add(library)
    db_session.flush()

    parent = Series(
        library_id=library.id,
        title="Solo Leveling",
        folder_path=str(series_dir.resolve()),
    )
    db_session.add(parent)
    db_session.flush()

    orphan = Series(
        library_id=library.id,
        title="Episode 13.5",
        folder_path=str(episode_dir.resolve()),
    )
    db_session.add(orphan)
    db_session.flush()

    orphan_chapter = Chapter(
        series_id=orphan.id,
        title="Side Story",
        number=13.5,
        folder_path=str(episode_dir.resolve()),
        page_count=1,
    )
    db_session.add(orphan_chapter)
    db_session.flush()
    db_session.add(
        Page(
            chapter_id=orphan_chapter.id,
            number=1,
            file_path=str(episode_dir / "001.jpg"),
        )
    )

    db_session.commit()

    removed = ImportCleanupService(db_session).merge_all_orphans_global()
    db_session.commit()

    assert removed == 1
    remaining = db_session.query(Series).all()
    assert len(remaining) == 1

    chapters = (
        db_session.query(Chapter)
        .filter(Chapter.series_id == parent.id)
        .all()
    )
    assert len(chapters) == 1
    assert chapters[0].number == 13.5
    assert chapters[0].title == "Side Story"
