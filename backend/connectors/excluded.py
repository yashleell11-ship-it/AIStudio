"""Source IDs omitted from the active connector registry.

Only sources that still have connector code (or legacy aliases) but must not
register. Madara dead sites were removed from ``catalog.py`` instead.
"""

from __future__ import annotations

EXCLUDED_CONNECTORS: frozenset[str] = frozenset({
    # --- External / never catalogued ----------------------------------------
    "comick",
    "bato",  # shut down Jan 2026
    "cartoonmad",  # Afternic parked
    "dragontea",  # Cloudflare JS wall
    "comix_to",  # signed API; blocks server access
    "gingertoon",  # CF-protected admin-ajax catalog
    "hentai3z",  # placeholder stub
    "hentaiyes",  # affiliate hub, no catalog
    # --- Hand-crafted but dead (code kept for fixtures) -----------------------
    "1stkissmanga",  # 1stkissmanga.io parked / unreachable
})
