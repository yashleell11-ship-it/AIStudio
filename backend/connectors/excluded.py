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
    # Deregistered 2026-09-04 after an end-to-end probe from the VPS. Each of
    # these could only ever error in the UI, so leaving them registered cost
    # users a broken source rather than buying us an eventual recovery.
    "coffeemanga",  # coffeemanga.ink 404s every path (/, /manga/, sitemap, wp-json)
    "harimanga",  # harimanga.vip TLS handshake aborts; .com redirects to a lander
})
