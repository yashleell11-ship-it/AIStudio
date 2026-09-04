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
    # Deregistered 2026-09-04 after the speed/health audit. Every request to
    # the apex read-times-out (91.7s before giving up -- it was the single
    # slowest thing in the registry, and it only ever produced an error), and
    # www.cmanhua.com now serves the stock "IIS Windows Server" placeholder,
    # so there is no origin left to fix a connector against.
    "cmanhua",
    # Deregistered 2026-09-05 after an end-to-end probe from the VPS. Weeb
    # Central itself is healthy from here -- browse, search, detail and
    # chapters all pass in about two seconds -- but two of the four CDN zones
    # it shards page images across, official.lowee.us and scans.lastation.us,
    # answer this deployment's OVH address with a Cloudflare WAF block page:
    # "Sorry, you have been blocked", our own IP echoed back, and no challenge
    # to solve. It is the egress IP and nothing else. Measured from inside the
    # production container, every one of these 403s on both zones and 200s on
    # hot.planeptune.us over the identical code path: a bare GET, the
    # connector's Referer + User-Agent, a full browser header block
    # (Accept/Accept-Language/Sec-Fetch-*/UA-CH), and four curl_cffi
    # impersonation profiles across Chrome, Safari and Firefox. The same bare
    # GET from a residential line returns the PNG. The zones are not mirrors
    # of each other -- a blocked path 404s on the reachable planeptune.us and
    # compsci88.com hosts -- and the container has no IPv6 route to try their
    # AAAA records from. Sampled serially the same day: of the 21 series on
    # browse page 1 (Latest Updates) that resolved to a page URL, all 21 were
    # on a blocked zone, and 7 of 20 on the Popularity page were. So the
    # default catalogue is unreadable here, and the connector cannot tell a
    # readable series from an unreadable one until the reader is already open
    # on broken images. Delete this line the day the deployment reads from
    # residential egress; the connector and its fixtures are untouched and
    # still pass.
    "weebcentral",
})
