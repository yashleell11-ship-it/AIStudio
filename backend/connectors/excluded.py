"""Source IDs omitted from the active connector registry."""

from __future__ import annotations

EXCLUDED_CONNECTORS: frozenset[str] = frozenset({
    "comick",
    "allhenscan",  # allhenscan.com — domain dead (NXDOMAIN)
    "1stkissmanga",  # 1stkissmanga.io — parked / unreachable
    "asiatoon",  # asiatoon.net — Cloudflare JS challenge blocks server access
    "bato",  # bato.to — site shut down Jan 2026; primary times out; mirrors parked/404/CF JS
    "cartoonmad",  # cartoonmad.com — Afternic parked (/lander stub); no live catalog
    "dragontea",  # dragontea.ink — Cloudflare JS challenge blocks server access
    "comix_to",  # comix.to — jscrambler-signed /api/v1; blocks server access
    "gingertoon",  # gingertoon.com — empty SSR archive; catalog loaded via CF-protected admin-ajax
    "hentai3z",  # hentai3z.com — placeholder stub (~480 bytes); no browseable catalog
    "hentaiyes",  # hentaiyes.com — affiliate link hub; no on-site manga catalog
})
