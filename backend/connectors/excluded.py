"""Source IDs omitted from the active connector registry."""

from __future__ import annotations

EXCLUDED_CONNECTORS: frozenset[str] = frozenset({
    "comick",
    "allhenscan",  # allhenscan.com — domain dead (NXDOMAIN)
    "1stkissmanga",  # 1stkissmanga.io — parked / unreachable
    "asiatoon",  # asiatoon.net — Cloudflare JS challenge blocks server access
})
