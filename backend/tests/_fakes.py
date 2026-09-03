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

    ``listings`` maps ``(source_id, sort, genre, page)`` (sort/genre as ``""``
    when absent) -> a serialized paginated listing dict, mirroring what
    ``BrowseService.list_series`` returns for a plain browse.

    ``mature_sources`` + ``gate_open`` mirror the per-caller 18+ gate:
    ``ensure_visible`` raises the same not-found ``AppError`` the real service
    does for a mature source while the gate is closed.
    """

    def __init__(
        self,
        series: dict[tuple[str, str], dict[str, Any]] | None = None,
        listings: dict[tuple[str, str, str, int], dict[str, Any]] | None = None,
    ):
        self.series = series or {}
        self.listings = listings or {}
        self.down = False
        self.calls: list[str] = []
        self.mature_sources: set[str] = set()
        self.gate_open = True

    # --- gate ---------------------------------------------------------
    def _gate_open(self) -> bool:
        return self.gate_open

    def ensure_visible(self, source_id: str) -> None:
        """Registry-only check — works even when the connector is ``down``."""
        if source_id in self.mature_sources and not self.gate_open:
            from core.errors import AppError

            raise AppError(
                "Source not found.", code="source_not_found", status_code=404
            )

    # --- browse listing ----------------------------------------------
    def list_series(
        self,
        source_id: str,
        *,
        page: int = 1,
        query: str | None = None,
        sort: str | None = None,
        genre: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            f"list_series:{source_id}?page={page}&sort={sort}&genre={genre}"
            f"&query={query}"
        )
        if self.down:
            raise RuntimeError("connector down")
        key = (source_id, sort or "", genre or "", page)
        try:
            import json as _json

            return _json.loads(_json.dumps(self.listings[key]))  # deep copy
        except KeyError as exc:  # noqa: TRY003
            raise LookupError(f"no listing fixture for {key}") from exc

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
