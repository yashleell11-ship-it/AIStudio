"""Facade for working with source connectors without exposing implementation details."""

from __future__ import annotations

from connectors.adapters import build_scan_result
from connectors.base import SourceConnector
from connectors.local_filesystem.scanner import ScanResult
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.registry import create_connector

DEFAULT_SOURCE_TYPE = "local_filesystem"


class SourceService:
    """Routes content discovery through registered source connectors."""

    def __init__(self, source_type: str = DEFAULT_SOURCE_TYPE) -> None:
        self._source_type = source_type

    def create_connector(self, **config: object) -> SourceConnector:
        return create_connector(self._source_type, **config)

    def discover_folder(self, folder_path: str) -> ScanResult:
        """Discover all content under a folder using the configured connector."""
        connector = self.create_connector(root_path=folder_path)
        return build_scan_result(connector)

    def get_series_list(self, page: int, **config: object) -> PaginatedSeriesList:
        connector = self.create_connector(**config)
        return connector.get_series_list(page)

    def get_series(self, series_id: str, **config: object) -> Series | None:
        connector = self.create_connector(**config)
        return connector.get_series(series_id)

    def get_chapters(self, series_id: str, **config: object) -> list[Chapter]:
        connector = self.create_connector(**config)
        return connector.get_chapters(series_id)

    def get_chapter_pages(self, chapter_id: str, **config: object) -> list[Page]:
        connector = self.create_connector(**config)
        return connector.get_chapter_pages(chapter_id)
