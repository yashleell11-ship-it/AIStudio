"""``_locate`` and ``_assemble`` scan instead of materializing every key.

A 4,000-chapter series (novelfull, baozimh) had a key built for every chapter
just to find one — and ``_assemble`` is called once per chapter in a bulk
window, so a 20-chapter window built 80,000 strings to name 40 of them.

Both are pure functions on the chapter list, so the risk is not performance:
it is that a rewritten match changes WHICH chapter is found. These tests state
the contract independently of the implementation, including the parts that are
easy to lose — the two-pass order, and the slash tolerance.
"""

from __future__ import annotations

from services.reader_service import ReaderService, _chapter_key, _locate


def _chapters(*keys: str) -> list[dict[str, object]]:
    return [
        {"key": key, "number": float(i + 1), "title": f"Chapter {i + 1}"}
        for i, key in enumerate(keys)
    ]


def _reference_locate(chapters, chapter_key: str) -> int:
    """The implementation this replaced, kept as the oracle."""
    keys = [_chapter_key(c) for c in chapters]
    try:
        return keys.index(chapter_key)
    except ValueError:
        target = chapter_key.strip("/")
        return next((i for i, k in enumerate(keys) if k.strip("/") == target), -1)


def test_locate_matches_the_reference_on_every_key() -> None:
    chapters = _chapters("a", "/b", "c/", "/d/", "e")
    probes = ["a", "/b", "b", "c/", "c", "/d/", "d", "e", "zz", "", "/"]
    for probe in probes:
        assert _locate(chapters, probe) == _reference_locate(chapters, probe), probe


def test_an_exact_match_late_beats_a_slash_match_early() -> None:
    """The two-pass order is load-bearing, not incidental."""
    chapters = _chapters("/ch-1/", "ch-1")
    assert _locate(chapters, "ch-1") == 1
    assert _reference_locate(chapters, "ch-1") == 1


def test_a_missing_chapter_is_minus_one() -> None:
    assert _locate(_chapters("a", "b"), "c") == -1
    assert _locate([], "a") == -1


def test_entries_keyed_by_id_rather_than_key_still_locate() -> None:
    """Connector-shaped entries use ``id``; cache-shaped ones use ``key``."""
    chapters = [{"id": "x-1"}, {"key": "x-2"}]
    assert _locate(chapters, "x-1") == 0
    assert _locate(chapters, "x-2") == 1


def test_assemble_names_the_right_neighbours() -> None:
    chapters = _chapters("c1", "c2", "c3")
    pages = [{"number": 1, "image_url": "/proxy/1"}]

    first = ReaderService._assemble("src", "series", "c1", chapters, 0, pages)
    middle = ReaderService._assemble("src", "series", "c2", chapters, 1, pages)
    last = ReaderService._assemble("src", "series", "c3", chapters, 2, pages)

    assert (first["prev"], first["next"]) == (None, "c2")
    assert (middle["prev"], middle["next"]) == ("c1", "c3")
    assert (last["prev"], last["next"]) == ("c2", None)


def test_assemble_on_a_single_chapter_series_has_no_neighbours() -> None:
    payload = ReaderService._assemble(
        "src", "series", "only", _chapters("only"), 0, []
    )
    assert payload["prev"] is None
    assert payload["next"] is None
    assert payload["page_count"] == 0


def test_assemble_still_carries_the_chapter_number_and_pages() -> None:
    chapters = _chapters("c1", "c2")
    pages = [
        {"number": 1, "image_url": "/proxy/a"},
        {"number": 2, "image_url": "/proxy/b"},
    ]
    payload = ReaderService._assemble("src", "series", "c2", chapters, 1, pages)
    assert payload["chapter_number"] == 2.0
    assert payload["page_count"] == 2
    assert payload["pages"] == [
        {"number": 1, "url": "/proxy/a"},
        {"number": 2, "url": "/proxy/b"},
    ]
