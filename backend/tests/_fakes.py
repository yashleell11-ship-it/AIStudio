"""Shared connector/browse stubs for the source-native service tests."""

from __future__ import annotations

from typing import Any


class FakeBrowse:
    """A stand-in for ``BrowseService`` with canned per-series data.

    ``series`` maps ``(source_id, series_key)`` -> ``{"meta": {...},
    "chapters": [{"id","number","title",...}], "pages": {chapter_key: [
    {"number","image_url"}]}}``. Any unknown key raises ``LookupError`` unless
    ``down`` is set, in which case every call raises ``RuntimeError`` (connector
    down).
    """

    def __init__(self, series: dict[tuple[str, str], dict[str, Any]] | None = None):
        self.series = series or {}
        self.down = False
        self.calls: list[str] = []

    # --- helpers ------------------------------------------------------
    def _entry(self, source_id: str, series_key: str) -> dict[str, Any]:
        if self.down:
            raise RuntimeError("connector down")
        try:
            return self.series[(source_id, series_key)]
        except KeyError as exc:  # noqa: TRY003
            raise LookupError(f"no fixture for {source_id}/{series_key}") from exc

    # --- BrowseService surface --------------------------------------
    def get_series(self, source_id: str, series_key: str) -> dict[str, Any]:
        self.calls.append(f"get_series:{source_id}/{series_key}")
        return dict(self._entry(source_id, series_key).get("meta", {}))

    def get_chapters(self, source_id: str, series_key: str) -> list[dict[str, Any]]:
        self.calls.append(f"get_chapters:{source_id}/{series_key}")
        return list(self._entry(source_id, series_key).get("chapters", []))

    def get_chapter_pages(self, source_id: str, chapter_key: str) -> list[dict[str, Any]]:
        self.calls.append(f"get_chapter_pages:{source_id}/{chapter_key}")
        for entry in self.series.values():
            pages = entry.get("pages", {})
            if chapter_key in pages:
                return list(pages[chapter_key])
        return []
