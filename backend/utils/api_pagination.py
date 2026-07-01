"""Shared pagination aliases and list metadata for consistent API responses.

Mobile and desktop clients historically used different field names across
endpoints. This module adds aliases without removing canonical fields.
"""

from __future__ import annotations

import math
from typing import Any

from starlette.responses import Response

HEADER_LIST_TOTAL = "X-Total-Count"
HEADER_PROGRESS_FOUND = "X-Progress-Found"


def enrich_pagination_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    """Return *payload* with cross-endpoint pagination field aliases."""
    out = dict(payload)

    per_page = out.get("per_page")
    page_size = out.get("page_size")
    limit = out.get("limit")
    page = out.get("page")
    offset = out.get("offset")
    total = out.get("total", 0)

    if per_page is not None and page_size is None:
        out["page_size"] = per_page
    elif page_size is not None and per_page is None:
        out["per_page"] = page_size

    effective_size = out.get("per_page") or out.get("page_size") or limit
    if limit is not None:
        if out.get("per_page") is None:
            out["per_page"] = limit
        if out.get("page_size") is None:
            out["page_size"] = limit

    if page is None and offset is not None and effective_size:
        out["page"] = offset // effective_size + 1
    if offset is None and page is not None and effective_size:
        out["offset"] = max(0, (page - 1) * effective_size)
    if out.get("limit") is None and effective_size is not None:
        out["limit"] = effective_size

    has_next = out.get("has_next")
    has_more = out.get("has_more")
    if has_next is not None and has_more is None:
        out["has_more"] = has_next
    elif has_more is not None and has_next is None:
        out["has_next"] = has_more
    elif has_next is None and has_more is None and effective_size:
        current_page = out.get("page", 1)
        current_offset = out.get("offset")
        if current_offset is not None:
            consumed = current_offset + effective_size
        else:
            consumed = current_page * effective_size
        computed = consumed < total
        out["has_next"] = computed
        out["has_more"] = computed

    if total is not None and effective_size and out.get("total_pages") is None:
        out["total_pages"] = math.ceil(total / effective_size) if effective_size else 0

    return out


def set_list_total_header(response: Response, total: int) -> None:
    """Expose list cardinality for endpoints that return bare arrays."""
    response.headers[HEADER_LIST_TOTAL] = str(max(0, total))


def set_progress_found_header(response: Response, found: bool) -> None:
    """Indicate whether reading progress exists when the body may be null."""
    response.headers[HEADER_PROGRESS_FOUND] = "true" if found else "false"
