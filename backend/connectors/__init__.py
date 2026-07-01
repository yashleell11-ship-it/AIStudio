"""Pluggable source connectors for discovering series, chapters, and pages."""

from connectors.adapters import build_scan_result
from connectors.base import SourceConnector
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.registry import (
    create_connector,
    get_connector,
    list_connector_types,
    register_connector,
)

__all__ = [
    "Chapter",
    "Page",
    "PaginatedSeriesList",
    "Series",
    "SourceConnector",
    "build_scan_result",
    "create_connector",
    "get_connector",
    "list_connector_types",
    "register_connector",
]
