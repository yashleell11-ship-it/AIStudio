from __future__ import annotations

import pytest

from connectors.asurascans.mappers import chapter_item_to_chapter
from connectors.titles import normalize_chapter_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Real AsuraScans data: source-novel episode prefixes must be dropped.
        ("47. The Culprit (7)", "The Culprit (7)"),
        ("48.Heavenly Demon Inauguration (1)", "Heavenly Demon Inauguration (1)"),
        ("101. Border of Life and Death <2>", "Border of Life and Death <2>"),
        ("3) The Trap", "The Trap"),
        ("10.  Northbound (1)", "Northbound (1)"),
        # Whitespace-only cleanup for titles without a prefix.
        (" Four Symbols' Relic (4)", "Four Symbols' Relic (4)"),
        ("The Queen  #1 ", "The Queen #1"),
        # Titles that merely start with a number stay intact.
        ("1.5 Interlude", "1.5 Interlude"),
        ("1984 (1)", "1984 (1)"),
        ("The Queen #1", "The Queen #1"),
        # A bare counter is not stripped into an empty title.
        ("3.", "3."),
        # Nothing displayable -> None so callers can fall back.
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_chapter_title(raw: str | None, expected: str | None):
    assert normalize_chapter_title(raw) == expected


def test_asurascans_chapter_title_is_normalized_but_number_is_preserved():
    chapter = chapter_item_to_chapter(
        {"number": 134, "title": "47. The Culprit (7)", "page_count": 14},
        series_id="nano-machine-30e93729",
    )
    assert chapter.number == 134
    assert chapter.title == "The Culprit (7)"
    assert chapter.id == "nano-machine-30e93729:134"


def test_asurascans_untitled_chapter_falls_back_to_chapter_number():
    chapter = chapter_item_to_chapter(
        {"number": 134, "title": None, "page_count": 14},
        series_id="nano-machine-30e93729",
    )
    assert chapter.title == "Chapter 134"
