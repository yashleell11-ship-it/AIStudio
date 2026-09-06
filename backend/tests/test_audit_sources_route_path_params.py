"""Guard: two greedy ``:path`` params on one route silently mis-split its keys.

Starlette's ``:path`` converter matches through slashes, so on a route with two
of them the FIRST one wins every ambiguous character. ``.../series/{series_id:
path}/chapters/{chapter_id:path}/reader`` therefore broke the moment a chapter
id contained ``/chapters/`` itself -- which is exactly how aurorascans,
beehentai and comicland mint theirs -- and every chapter on those sources
answered "Chapter not found" until the handler re-split the key (see
``test_reader_route_chapters_segment``).

Only that one route is allowed to carry the shape, because only it undoes the
greedy split. A new route that adds a second ``:path`` fails here rather than
in production.
"""

from __future__ import annotations

import re

from routes.sources import router

_PATH_PARAM = re.compile(r"\{[^{}]+:path\}")

# The one route that compensates, in ``_split_at_first_chapters_segment``.
_COMPENSATED = {
    "/sources/{source_id}/series/{series_id:path}/chapters/{chapter_id:path}/reader"
}


def test_no_new_sources_route_carries_two_greedy_path_params():
    greedy = {
        route.path: len(_PATH_PARAM.findall(route.path))
        for route in router.routes
        if len(_PATH_PARAM.findall(getattr(route, "path", ""))) > 1
    }

    assert set(greedy) == _COMPENSATED, (
        "a route has two greedy :path params and does not re-split its keys: "
        f"{sorted(set(greedy) - _COMPENSATED)}"
    )
