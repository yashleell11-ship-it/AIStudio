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
    # Removed 2026-09-05 after the VPS probe died in the TLS handshake, not in
    # HTTP:
    #   manhuakey - the registration expired 2026-09-04T08:48:55Z and Namecheap
    #               repointed the name 13 hours later, so .com now delegates
    #               manhuakey.com to dns101/dns102.registrar-servers.com and
    #               every public resolver answers with the parking lander's
    #               IPs. That host carries no certificate for the name, so it
    #               completes the TCP connect and then drops the ClientHello --
    #               the UNEXPECTED_EOF_WHILE_READING the probe reported. It
    #               drops it identically under OpenSSL and under curl_cffi's
    #               BoringSSL impersonation, with SNI and without, and at a
    #               forced TLS 1.2, so use_cf=True was never going to save it.
    #               Port 80 does answer, with a Namecheap "registration has
    #               expired" ad page. The WordPress origin is still up behind
    #               Cloudflare but only stale DNS still points at it; from the
    #               VPS a pinned Cloudflare IP answers 403. Restoring this is
    #               one line if the owner renews inside the redemption window.
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
    # Added 2026-09-05 (shard 5) after an end-to-end probe from the VPS.
    # Stock Madara: /manga/ listing, the per-series ``ajax/chapters/`` POST
    # and 55 wp-manga-chapter-img pages all answered, and every page image is
    # self-hosted, so the host-derived allowlist already covers them.
    # Non-mature on evidence rather than assumption: /manga-genre/adult/,
    # /mature/, /smut/ and /ecchi/ all 404 and the live taxonomy is only
    # drama, gyaru, psychological and romance. Small library, ~80 series.
    _site("kokomangas", "KokoMangas", "kokomangas.com"),
    # Madara under a renamed theme directory (themes/linkmanga), so it
    # fingerprints on wp-manga/page-item-detail, not on the theme path. Its
    # own ``{series}/ajax/chapters/`` soft-fails by returning the whole page,
    # so the /wp-admin/admin-ajax.php manga_get_chapters flow is the one that
    # works here. Lists start at ch-001, so the full backlog is reachable --
    # not the mangagg 24-chapter trap. mature=True is positively established:
    # /manga-genre/adult/, /mature/, /smut/ and /ecchi/ each return 200 with
    # populated series, and sampled titles are adult manhwa. A minority of
    # series (e.g. vigilante-part-2) point their page images at
    # f1link.linkmanga.com and those files are genuinely missing (nginx 404);
    # allowlisting the host keeps the SSRF guard from stacking a second,
    # more confusing failure on top of the 404.
    _site("linkmanga", "LinkManga", "linkmanga.com", mature=True, extra_image_hosts=frozenset({"f1link.linkmanga.com"})),
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
    # Added 2026-09-05 after an end-to-end probe from the VPS. Three sibling
    # installs from one operator (identical Madara title template) whose
    # catalogues are niche-partitioned -- western parody comics, futanari,
    # yuri -- with fully disjoint slug sets, so they complement each other and
    # allporncomic rather than duplicating them. Plain curl cleared browse,
    # series and chapter on all three from the OVH egress, so use_cf=False
    # buys the cheaper client; every cover and page image is self-hosted under
    # /wp-content/uploads/, so the host-derived allowlist already covers them
    # and no extra_image_hosts are needed. Chapters come from the per-series
    # ``{series}/ajax/chapters/`` endpoint -- admin-ajax.php answers
    # manga_get_chapters with 400 on all three, so the connector settles on
    # the relative shape after one probe.
    #
    # hentaixcomic and hentaixyuri ship the simple-cloudflare-turnstile plugin
    # (hentaixyuri also honeypot + page-links-to) and reference
    # challenges.cloudflare.com, but it gated no read path from the VPS -- it
    # appears to guard only the comment/login forms. Flip these to use_cf=True
    # if browse ever starts coming back as a challenge page.
    _site("hentaixcomic", "HentaiXComic", "hentaixcomic.com", mature=True, use_cf=False),
    _site("hentaixdickgirl", "HentaiXDickgirl", "hentaixdickgirl.com", mature=True, use_cf=False),
    _site("hentaixyuri", "HentaiXYuri", "hentaixyuri.com", mature=True, use_cf=False),
    # jinmangas.com is nothing but a 301 to this name, so the redirect target
    # is what gets registered. Textbook Madara behind Cloudflare with no
    # challenge; the per-series ajax/chapters/ endpoint returned 60 chapters
    # and every cover is on mangafree.info itself. Mature: the catalogue is
    # uncensored 18+ manhwa throughout.
    _site("mangafree", "MangaFree", "mangafree.info", mature=True),
    # Added 2026-09-05 after end-to-end probes from the VPS egress. All five
    # are stock Madara (wp-content/themes/madara plus a child theme) and
    # cleared browse/search/detail/chapters/pages/image-bytes on the plain
    # SyncConnectorHttpClient, so use_cf=False buys the cheaper client. Each
    # one's /wp-admin/admin-ajax.php answers manga_get_chapters with 400, so
    # like mangasushi above they settle on the per-series
    # ``{series}/ajax/chapters/`` shape after a single probe.
    #
    # The four non-mature entries are general manga/manhwa/manhua aggregators
    # whose Adult/Mature genres are a small slice of an otherwise mainstream
    # catalogue (mangayy: 16 + 75 listing pages out of 1096), with no 18+
    # interstitial — the same line already drawn for mangaread/manhuaplus/
    # mangasushi. mangamaniacs is the opposite case and is flagged.
    #
    # Explicitly yaoi/smut: the site titles itself "Read the best yaoi manga
    # and manhwa online for free" and the first sampled series carries
    # Omegaverse + Smut, so mature is not a judgement call here. Page images
    # sit on an images.* sibling the host-derived allowlist does not reach;
    # covers are on the apex. Cosmetic wart: page 1's pagination advertises
    # only page 2 so the reported total is wrong, but each page advertises the
    # next, so api_has_more still walks the (deep) catalogue forward.
    _site("mangamaniacs", "MangaManiacs", "mangamaniacs.org", mature=True, use_cf=False, extra_image_hosts=frozenset({"images.mangamaniacs.org"})),
    # Series live at /read-1/<slug>/, so the segment is the whole trick; that
    # path paginates natively to page 222 (~3300 series) and needs no
    # listing_post_type override. This zone's bot-fight rule is header-shape
    # sensitive — a UA-only httpx GET is answered 403 while the production
    # client's own header block passed every request — so use_cf=False is
    # correct but the default headers are load-bearing here.
    _site("mangaowl", "MangaOwl", "mangaowl.io", url_segment="read-1", use_cf=False),
    # 4 of 9 sampled chapters serve their pages from u1.manhuatop.org, and
    # every chapter also embeds a manhuatop.org promo banner inside a
    # wp-manga-chapter-img tag that the mapper extracts as a page — without
    # that host the image proxy rejects those pages before requesting them.
    # Pagination is a sliding window (page N links N-1..N+1), so the reported
    # total is meaningless; browse still walks forward one page at a time.
    _site("mangatop", "MangaTop", "mangatop.org", url_segment="series", use_cf=False, extra_image_hosts=frozenset({"manhuatop.org"})),
    # Same operator network as mangatop (both hotlink its theme assets) but a
    # genuinely different catalogue: 3-4 shared slugs across the first two
    # listing pages, 741 pages of its own. Distinct from the manhwatop.com
    # entry above — different site, different segment, one letter apart. Its
    # image subdomains (s2/s3/u1) are all its own, so the host-derived
    # allowlist already covers them.
    _site("manhuatop", "ManhuaTop", "manhuatop.org", url_segment="manhua", use_cf=False),
    # Deepest catalogue of the batch: 1096 listing pages at 36 cards each.
    # Every sampled page image came off like.mgread.io, so that extra host is
    # mandatory or the image proxy blocks every page before it is requested.
    # One oddity, reproducible across two runs: page/5/ repeats 33 of page/1/'s
    # 36 cards while pages 2/3/40 are mutually disjoint.
    _site("mangayy", "MangaYY", "mangayy.org", use_cf=False, extra_image_hosts=frozenset({"like.mgread.io"})),
    #
    # Also probed 2026-09-05 and DELIBERATELY NOT ADDED. Do not re-add without
    # re-probing from the VPS:
    #   mangazin.org - works, but it is mangatop.org's weaker twin rather than
    #               a second source. Listing pages 1+2 share 23 of 25 slugs
    #               with it, both hotlink manhuatop.org theme assets, and the
    #               same chapter resolves to the same storage path
    #               (manga_6ed26d1f…/chapter_0/ch_0_1.jpg) on both, differing
    #               only in CDN hostname. Where mangatop returned 9/9 on
    #               sampled image fetches, mangazin's older chapters point at
    #               cdn-2.mangazin.org, which 404s every path tried — mangatop
    #               serves those same chapters fine from st-2.
    #   mangatx.cc - not Madara: Themesia (eplister/chapternum/bixbox, no
    #               wp-manga markup), so it needs a bespoke connector rather
    #               than a catalog line, and it would be mature=True (the
    #               front page leads with uncensored 18+ manhwa and the pages
    #               are hosted on manga18.us). Worth writing if someone wants
    #               it — the series page server-renders the complete chapter
    #               list (3876 chapters on Martial Peak, no ajax) and the
    #               reader emits plain <img src>. The blocker is discovery:
    #               no working listing pagination was found (/manga-list/ tops
    #               out at 43 series, page 2 302s to the homepage) and /?s=
    #               returns a link set indistinguishable from the homepage's.
    #   manhuagui.com - custom Chinese CMS (Kanmanhua), not WordPress. Deep,
    #               general-audience, and it answers the VPS cleanly from a
    #               bare non-Cloudflare origin, but the reader ships ~7KB of
    #               packed JS (window["\x65\x76\x61\x6c"], SMH.imgData) and the
    #               i.hamreus.com URLs it unpacks to carry signed query
    #               params, so pages cannot be scraped with the regex every
    #               Madara source uses. Needs a JS unpacker plus signature
    #               handling.
    # Added 2026-09-05 after an end-to-end probe from the VPS. Madara
    # (themes/madara + madara-child) on url_segment "adult-comics": this install
    # answers 200 with the 100815-byte homepage for every unknown path, so the
    # segment had to be read off real series hrefs rather than probed. Chapters
    # are inline on the series page (its relative ajax/chapters/ endpoint 400s),
    # which the connector's inline fallback already covers, and every page image
    # is on comicsvalley.com itself. Left at use_cf=True: the homepage is served
    # from Cloudflare APO cache, so a plain client clearing a cache HIT says
    # nothing about what a MISS would do.
    #
    # NOT a second registration of the hand-crafted ``comicsvalley`` connector:
    # that one reads comicsvalley.NET (/manga/, manga-genre taxonomies,
    # translated doujin/manhwa). This is a separate WordPress install by the
    # same operator - comic-genre/comic-tag taxonomies, western/Indian 3DX
    # library, and .com slugs 302 on .net. The display name carries the TLD
    # because the operator brands both sites "Comics Valley".
    _site("comicsvalleycom", "ComicsValley (.com)", "comicsvalley.com", url_segment="adult-comics", mature=True),
    # Stock Madara on url_segment "porncomic" (/manga/ 404s). admin-ajax
    # answers manga_get_chapters with 400, so the connector settles on the
    # relative ``{series}/ajax/chapters/`` shape after one probe, exactly like
    # mangasushi; plain httpx cleared every stage from the OVH egress with no
    # challenge, so use_cf=False buys the cheaper client. Covers and page images
    # are all self-hosted, so the host-derived allowlist covers them.
    _site("gedecomix", "GEDE Comix", "gedecomix.com", url_segment="porncomic", mature=True, use_cf=False),
)
# fmt: on

# Alias — entire catalog is production-safe after prune.
MADARA_LIVE: frozenset[str] = frozenset(s.source_id for s in MADARA_CATALOG)

HANDCRAFTED_CONNECTORS: frozenset[str] = frozenset({
    "mangadex", "asurascans", "mangakatana", "demonicscans", "nhentai",
    "18porncomic", "3hentai", "8muses", "akuma", "asmhentai", "aurorascans", "beehentai",
    "baozimh", "comicasura", "comicsvalley", "comicland", "doujins", "ehentai", "elftoon", "flamescans",
    "freeadultcomix", "galaxymanga", "hentai20", "hentaifox", "hentaiera",
    "webtoons", "weebcentral", "tapas",
})
