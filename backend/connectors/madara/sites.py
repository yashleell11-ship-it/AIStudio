"""Madara-theme site catalog — live-probed entries only."""

from __future__ import annotations

from connectors.madara.config import MadaraSiteConfig


def _site(
    source_id: str,
    display_name: str,
    domain: str,
    *,
    url_segment: str = "manga",
    mature: bool = False,
    use_cf: bool = True,
    extra_image_hosts: frozenset[str] = frozenset(),
) -> MadaraSiteConfig:
    return MadaraSiteConfig(
        source_id=source_id,
        display_name=display_name,
        base_url=f"https://{domain}",
        url_segment=url_segment,
        mature=mature,
        use_cf=use_cf,
        extra_image_hosts=extra_image_hosts,
    )


# fmt: off
# Live-probed 2026-07-11: 15 Madara sources (+ 6 hand-crafted).
MADARA_SITES: tuple[MadaraSiteConfig, ...] = (
    _site("mangaread", "MangaRead", "mangaread.org"),
    _site("manhuaplus", "ManhuaPlus", "manhuaplus.com", extra_image_hosts=frozenset({"cdn.manhuaplus.com"})),
    _site("manhuakey", "ManhuaKey", "manhuakey.com", use_cf=False),
    _site("topmanhua", "TopManhua", "topmanhua.net", use_cf=False, mature=True),
    _site("manhuahot", "ManhuaHot", "manhuahot.com", use_cf=False, mature=True),
    _site("manhuanext", "ManhuaNext", "manhuanext.com", use_cf=False, mature=True),
    _site("manhwaclub", "ManhwaClub", "manhwaclub.net", mature=True, use_cf=False),
    _site("manhwatop", "ManhwaTop", "manhwatop.com", mature=True, use_cf=False),
    _site("manhwaden", "ManhwaDen", "manhwaden.com", mature=True, use_cf=False),
    _site("manhwanex", "ManhwaNex", "manhwanex.com", mature=True, use_cf=False),
    _site("apcomics", "APComics", "apcomics.org", mature=True, use_cf=False),
    _site("cocomic", "CoComic", "cocomic.co", mature=True, use_cf=False),
    _site("manga18x", "Manga18x", "manga18x.net", mature=True, use_cf=False),
    _site("cucumbermanga", "CucumberManga", "cucumbermanga.com", mature=True, use_cf=False),
    _site("pawmanga", "PawManga", "pawmanga.com", mature=True, use_cf=False),
)
# fmt: on
