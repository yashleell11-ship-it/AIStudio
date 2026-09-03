"""Madara-factory source catalog — live connectors only.

Pruned 2026-07-27: dead/parked/CF-blocked sites removed after E2E probe.
"""

from __future__ import annotations

from connectors.madara.config import MadaraSiteConfig


def _site(
    source_id: str,
    display_name: str,
    domain: str,
    *,
    url_segment: str = "manga",
    listing_post_type: str | None = None,
    mature: bool = False,
    use_cf: bool = True,
    extra_image_hosts: frozenset[str] = frozenset(),
) -> MadaraSiteConfig:
    return MadaraSiteConfig(
        source_id=source_id,
        display_name=display_name,
        base_url=f"https://{domain}",
        url_segment=url_segment,
        listing_post_type=listing_post_type,
        mature=mature,
        use_cf=use_cf,
        extra_image_hosts=extra_image_hosts,
    )


# fmt: off
MADARA_CATALOG: tuple[MadaraSiteConfig, ...] = (
    # --- Live Madara sources (E2E verified 2026-07-27) ----------------------
    # Removed 2026-09-04 after an end-to-end probe from the VPS:
    #   pawmanga  - pawmanga.com is a fingerprint-redirect parking page, 0 series
    #   topmanhua - cdn.topmanhua.net is permanently 526 (CF cannot validate the
    #               origin cert) and topmanhua.com now 302s to a monetisation
    #               domain, so no page image can ever be served
    _site("mangaread", "MangaRead", "mangaread.org"),
    _site("manhuaplus", "ManhuaPlus", "manhuaplus.com", extra_image_hosts=frozenset({"cdn.manhuaplus.com"})),
    _site("manhuakey", "ManhuaKey", "manhuakey.com", use_cf=False),
    _site("manhuahot", "ManhuaHot", "manhuahot.com", use_cf=False, mature=True),
    _site("manhuanext", "ManhuaNext", "manhuanext.com", use_cf=False, mature=True),
    _site("manhwaclub", "ManhwaClub", "manhwaclub.net", mature=True, use_cf=False),
    _site("manhwatop", "ManhwaTop", "manhwatop.com", mature=True, use_cf=False),
    _site("manhwaden", "ManhwaDen", "manhwaden.com", mature=True, use_cf=False, extra_image_hosts=frozenset({"remanhwa.me"})),
    _site("manhwanex", "ManhwaNex", "manhwanex.com", mature=True, use_cf=False),
    _site("s2manga", "S2Manga", "s2read.com", use_cf=False),
    _site(
        "allporncomic",
        "AllPornComic",
        "allporncomic.com",
        url_segment="porncomic",
        mature=True,
        use_cf=False,
        extra_image_hosts=frozenset({"cdn.allporncomic.com"}),
    ),
    _site("apcomics", "APComics", "apcomics.org", mature=True, use_cf=False),
    _site("cocomic", "CoComic", "cocomic.co", mature=True, use_cf=False),
    # Serves its page images from its manhwaclub.net sibling, so the image
    # proxy's SSRF allowlist needs that host or every page is rejected before
    # a request is made (the site browses and paginates fine regardless).
    _site(
        "manga18x",
        "Manga18x",
        "manga18x.net",
        mature=True,
        use_cf=False,
        extra_image_hosts=frozenset({"manhwaclub.net"}),
    ),
    _site("cucumbermanga", "CucumberManga", "cucumbermanga.com", mature=True, use_cf=False),
    _site("lilymanga", "LilyManga", "lilymanga.net", url_segment="gl", mature=True, use_cf=False),
    _site("mangadistrict", "MangaDistrict", "mangadistrict.com", url_segment="series", listing_post_type="wp-manga", mature=True, use_cf=False),
)
# fmt: on

# Alias — entire catalog is production-safe after prune.
MADARA_LIVE: frozenset[str] = frozenset(s.source_id for s in MADARA_CATALOG)

HANDCRAFTED_CONNECTORS: frozenset[str] = frozenset({
    "mangadex", "asurascans", "mangakatana", "demonicscans", "toonily", "nhentai",
    "18porncomic", "3hentai", "8muses", "akuma", "asmhentai", "aurorascans", "bbato", "beehentai",
    "baozimh", "cmanhua", "comicasura", "comicsvalley", "comicland", "doujins", "ehentai", "elftoon", "flamescans",
    "freeadultcomix", "galaxymanga", "hentai20", "hentaifox", "hentaiera",
    "webtoons", "weebcentral", "tapas",
})
