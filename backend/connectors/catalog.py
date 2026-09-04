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
    #
    # Probed and DELIBERATELY NOT ADDED 2026-09-05 (all four fingerprinted as
    # Madara from the outside; three do not behave like it). Do not re-add
    # without re-probing from the VPS:
    #   kingofshojo.com - not Madara at all. Runs the Themesia "mangareader"
    #               theme: chapters live at the site root as
    #               /<series>-chapter-<n>/, there is no wp-manga markup, and
    #               admin-ajax.php answers manga_get_chapters with 400 "0".
    #               Needs a bespoke connector, not a catalog line.
    #   mangaeffect.com - a permanent 301 to www.mangaread.org for every path,
    #               i.e. a second domain for the `mangaread` entry above.
    #   mangagg.com - genuine Madara (url_segment "comic"), and browse/search/
    #               detail/pages/image bytes all work, but the install
    #               publishes only the newest 24 chapters of every series
    #               through every enumerable route (36/36 sampled series
    #               returned exactly 24, none starting at chapter 1; the
    #               chapter-1 URLs are live but unreachable from any listing).
    #               A source you can never start reading from the beginning.
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
    # Added 2026-09-05 after an end-to-end probe from the VPS container.
    # Real Madara (wp-content/themes/madara), /manga/ series pages, chapters
    # from the per-series ``{series}/ajax/chapters/`` endpoint — its
    # /wp-admin/admin-ajax.php answers manga_get_chapters with 400, so the
    # connector settles on the relative shape after one probe. Plain httpx
    # cleared every stage from the OVH egress (~120 requests, no challenge),
    # so use_cf=False buys the cheaper client; covers and page images are all
    # on mangasushi.org itself, so the host-derived allowlist already covers
    # them and no extra_image_hosts are needed. Genres are stock-Madara with
    # 2 adult-tagged series site-wide, so it stays a general (non-mature)
    # source like mangaread/manhuaplus.
    _site("mangasushi", "MangaSushi", "mangasushi.org", use_cf=False),
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
    "baozimh", "comicasura", "comicsvalley", "comicland", "doujins", "ehentai", "elftoon", "flamescans",
    "freeadultcomix", "galaxymanga", "hentai20", "hentaifox", "hentaiera",
    "webtoons", "weebcentral", "tapas",
})
