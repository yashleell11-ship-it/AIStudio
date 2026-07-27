"""Convert normalized connector objects into the internal scan format."""

from __future__ import annotations

from connectors.base import SourceConnector
from connectors.local_filesystem.scanner import (
    ScanResult,
    ScannedChapter,
    ScannedPage,
    ScannedSeries,
)


def build_scan_result(connector: SourceConnector) -> ScanResult:
    """Walk a connector via its public API and produce a scan result for persistence."""
    result = ScanResult()
    series_page = 1
    # Hard ceiling so a connector that always reports has_more (or repeats a
    # non-empty page) can never spin this catalog walk forever.
    max_pages = 1000

    while True:
        listing = connector.get_series_list(series_page)
        # A page with no items means the listing is exhausted regardless of what
        # ``has_more`` claims — otherwise a buggy connector returning
        # ``has_more=True`` with an empty page would loop indefinitely.
        if not listing.items:
            break
        for series in listing.items:
            scanned_series = ScannedSeries(
                title=series.title,
                folder_path=series.canonical_path or series.id,
                chapters=[],
            )

            for chapter in connector.get_chapters(series.id):
                pages = connector.get_chapter_pages(chapter.id)
                scanned_series.chapters.append(
                    ScannedChapter(
                        title=chapter.title,
                        number=chapter.number,
                        folder_path=chapter.folder_path,
                        archive_path=chapter.archive_path,
                        pages=[
                            ScannedPage(
                                number=page.number,
                                file_path=page.file_path or "",
                                archive_path=page.archive_path,
                                archive_member=page.archive_member,
                            )
                            for page in pages
                        ],
                    )
                )

            if scanned_series.chapters:
                result.series.append(scanned_series)

        if not listing.has_more or series_page >= max_pages:
            break
        series_page += 1

    result.series_count = len(result.series)
    result.chapter_count = sum(len(series.chapters) for series in result.series)
    result.page_count = sum(
        len(chapter.pages)
        for series in result.series
        for chapter in series.chapters
    )
    return result
