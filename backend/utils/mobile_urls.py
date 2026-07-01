"""Relative API paths for mobile clients (prepend configured base URL)."""


def series_cover_url(series_id: int) -> str:
    return f"/library/covers/{series_id}"


def page_image_url(page_id: int) -> str:
    return f"/reader/page/{page_id}/image"
