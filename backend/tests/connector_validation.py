from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ContextManager, Iterable

from connectors.base import SourceConnector
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from services.outbound_security import host_matches_allowlist


@dataclass(frozen=True, slots=True)
class ConnectorContractCase:
    """Minimal contract fixtures needed to validate a connector end-to-end."""

    source_type: str
    fixtures_dir: Path

    # Search
    search_query: str

    # Series/reader chain
    series_id: str
    reader_chapter_id: str

    # Expected metadata sanity
    expected_title_substring: str
    expected_image_host_substring: str

    # Chapters ordering and decimal support
    decimal_chapter_ids: tuple[str, ...] = ()
    ordering_probe_ids: tuple[str, ...] = ()
    adjacent_pairs: tuple[tuple[str, str], ...] = ()

    # Optional stronger validations (only when fixtures support them)
    expected_latest_first_id: str | None = None
    expected_popular_first_id: str | None = None
    expected_page2_first_id: str | None = None
    expected_search_ids: tuple[str, ...] = ()

    # Mock installer: patches connector network methods to use fixtures.
    mock: Callable[[SourceConnector], ContextManager[None]] | None = None


def _load_text(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / name).read_text(encoding="utf-8")


def _load_json(fixtures_dir: Path, name: str) -> dict[str, Any]:
    import json

    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


def _chapter_adjacent_ids(chapters: list[Chapter], chapter_id: str) -> tuple[str | None, str | None]:
    idx = next(i for i, ch in enumerate(chapters) if ch.id == chapter_id)
    prev_id = chapters[idx - 1].id if idx > 0 else None
    next_id = chapters[idx + 1].id if idx < len(chapters) - 1 else None
    return prev_id, next_id


def _assert_listing(listing: PaginatedSeriesList) -> None:
    assert listing.page >= 1
    assert listing.page_size > 0
    assert listing.total >= 0
    assert isinstance(listing.has_more, bool)
    assert listing.items, "expected non-empty series list"
    assert listing.items[0].id
    assert listing.items[0].title


def _assert_series_metadata(series: Series, *, expected_title_substring: str) -> None:
    assert series.id
    assert series.title
    assert expected_title_substring.casefold() in series.title.casefold()
    assert series.cover_url, "expected cover_url"


def _assert_pages(
    pages: list[Page],
    *,
    expected_host_substring: str,
    connector: SourceConnector,
) -> None:
    from urllib.parse import urlparse

    assert pages, "expected non-empty pages"
    assert pages[0].remote_url, "expected remote_url on pages"
    assert expected_host_substring in (pages[0].remote_url or "")
    assert pages[0].number == 1
    parsed = urlparse(pages[0].remote_url or "")
    assert parsed.scheme == "https"
    assert parsed.hostname
    assert host_matches_allowlist(parsed.hostname, connector.allowed_image_hosts)


def _assert_chapters_ordered(chapters: list[Chapter]) -> None:
    assert chapters, "expected non-empty chapters"
    assert all(ch.series_id for ch in chapters)
    assert all(ch.id for ch in chapters)
    assert all(ch.title for ch in chapters)
    assert all(ch.number is not None for ch in chapters), "chapter.number must be set for ordering"
    numbers = [ch.number for ch in chapters if ch.number is not None]
    assert numbers == sorted(numbers), "chapters must be returned in ascending order"


def _assert_decimal_chapters(chapters: list[Chapter], *, expected_ids: Iterable[str]) -> None:
    if not expected_ids:
        return
    by_id = {ch.id: ch for ch in chapters}
    for cid in expected_ids:
        assert cid in by_id, f"missing expected decimal chapter id: {cid}"
        ch = by_id[cid]
        assert ch.number is not None and ch.number % 1 != 0, f"expected decimal number for {cid}"


def _assert_ordering_probe(chapters: list[Chapter], *, probe_ids: tuple[str, ...]) -> None:
    if len(probe_ids) < 2:
        return
    indices = [next(i for i, ch in enumerate(chapters) if ch.id == cid) for cid in probe_ids]
    assert indices == sorted(indices), "probe ids must appear in ascending chapter order"


def _assert_adjacent_pairs(chapters: list[Chapter], *, pairs: tuple[tuple[str, str], ...]) -> None:
    for left, right in pairs:
        _prev, nxt = _chapter_adjacent_ids(chapters, left)
        assert nxt == right, f"next({left}) should be {right}"
        prev, _nxt = _chapter_adjacent_ids(chapters, right)
        assert prev == left, f"prev({right}) should be {left}"


def validate_connector_contract(case: ConnectorContractCase) -> None:
    connector = __import__("connectors.registry", fromlist=["create_connector"]).create_connector(case.source_type)
    assert connector.source_type == case.source_type
    assert connector.is_browsable is True

    @contextmanager
    def _no_mock(_: SourceConnector) -> ContextManager[None]:
        yield

    mock_ctx = case.mock(connector) if case.mock else _no_mock(connector)
    with mock_ctx:
        # Latest / popular / pagination
        latest = connector.get_series_list(1, sort="default")
        _assert_listing(latest)
        popular = connector.get_series_list(1, sort="popular")
        _assert_listing(popular)
        page2 = connector.get_series_list(2, sort="default")
        _assert_listing(page2)
        assert page2.page == 2

        if case.expected_latest_first_id:
            assert latest.items[0].id == case.expected_latest_first_id
        if case.expected_popular_first_id:
            assert popular.items[0].id == case.expected_popular_first_id
            assert latest.items[0].id != popular.items[0].id
        if case.expected_page2_first_id:
            assert page2.items[0].id == case.expected_page2_first_id

        # Search
        search = connector.search_series(case.search_query, 1)
        _assert_listing(search)
        if case.expected_search_ids:
            result_ids = {item.id for item in search.items}
            for expected in case.expected_search_ids:
                assert expected in result_ids
        else:
            assert any(case.search_query.casefold() in s.title.casefold() for s in search.items)

        # Metadata
        series = connector.get_series(case.series_id)
        assert series is not None, "expected series details"
        _assert_series_metadata(series, expected_title_substring=case.expected_title_substring)

        # Chapters: ordering + decimals + adjacent navigation
        chapters = connector.get_chapters(case.series_id)
        _assert_chapters_ordered(chapters)
        _assert_decimal_chapters(chapters, expected_ids=case.decimal_chapter_ids)
        _assert_ordering_probe(chapters, probe_ids=case.ordering_probe_ids)
        _assert_adjacent_pairs(chapters, pairs=case.adjacent_pairs)

        # Reader
        pages = connector.get_chapter_pages(case.reader_chapter_id)
        _assert_pages(
            pages,
            expected_host_substring=case.expected_image_host_substring,
            connector=connector,
        )
        assert connector.find_page(pages[0].id) == pages[0]

