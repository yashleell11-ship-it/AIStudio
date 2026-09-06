"""The reader route must not split a chapter id at the id's own ``/chapters/``.

Three connectors (aurorascans, beehentai, comicland) build chapter ids as
``<series>/chapters/<chapter>``, so the reader URL carries two ``/chapters/``
segments. Both path params are greedy ``:path`` converters, and the first
one wins, so the series id swallowed ``…/chapters/<series>`` and the chapter
id arrived as the bare ``chapter-1`` -- which no listed chapter matches, and
the reader answered "Chapter not found" for every chapter on those sources
(production log, 2026-09-07).
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi.testclient import TestClient

from main import create_app
from services.reader_service import get_reader_service


class _SeenReader:
    def __init__(self) -> None:
        self.seen: tuple[str, str] | None = None

    def resolve_source_chapter(self, source_id, series_id, chapter_id):
        self.seen = (series_id, chapter_id)
        return {"pages": []}


def _client(reader: _SeenReader) -> TestClient:
    app = create_app(run_workers=False)
    app.dependency_overrides[get_reader_service] = lambda: reader
    return TestClient(app)


def test_chapter_id_containing_chapters_segment_reaches_the_reader_intact():
    reader = _SeenReader()
    series = "the-money-keeps-piling-up-even-if-i-spend-it"
    chapter = f"{series}/chapters/chapter-1"
    # The web client encodes each segment separately, so the slashes are
    # literal in the path exactly as the production log shows them.
    encoded = "/".join(quote(part, safe="") for part in chapter.split("/"))

    response = _client(reader).get(
        f"/sources/aurorascans/series/{quote(series, safe='')}/chapters/{encoded}/reader"
    )

    assert response.status_code == 200
    assert reader.seen == (series, chapter)


def test_plain_slash_bearing_chapter_ids_still_route_the_same_way():
    reader = _SeenReader()
    series = "group/solo-leveling"
    chapter = "vol/1/ch/2"

    response = _client(reader).get(
        f"/sources/mangadex/series/{quote(series, safe='')}/chapters/"
        f"{quote(chapter, safe='')}/reader"
    )

    assert response.status_code == 200
    assert reader.seen == (series, chapter)
