"""Probe a batch of source connectors for browse listing health."""

from __future__ import annotations

from connectors.excluded import EXCLUDED_CONNECTORS
from connectors.registry import create_connector

SOURCES = [
    "harimanga",
    "hentai20",
    "hentai2read",
    "hentai3z",
    "hentai4free",
    "hentaicity",
    "hentaiera",
    "hentaifox",
    "hentaihand",
    "hentaihere",
    "hentaiyes",
    "heytoon",
    "hiperdex",
    "hitomi",
    "honeytoon",
    "kingofshojo",
    "kingcomix",
    "lezhin",
    "likemanga",
    "lilymanga",
    "luminousscans",
    "lunatoons",
    "luscious",
    "lustoon",
    "manga18x",
    "mangabat",
    "mangabuddy",
    "mangaclash",
    "mangacute",
    "mangadass",
    "mangademon",
    "mangadex",
    "mangadistrict",
    "mangafire",
    "mangafreak",
    "mangago",
    "mangahere",
    "mangahub",
    "mangajar",
    "mangakakalot",
    "mangakakalotfun",
    "mangakatana",
    "mangakiss",
    "mangakomi",
    "manganato",
    "manganelo_link",
    "mangapark",
    "mangapill",
    "mangaread",
    "mangareader_to",
    "mangasect",
    "mangasee",
    "mangatoon",
    "mangatx",
    "manhuabox",
    "manhuafans",
    "manhuafast",
    "manhuagui",
    "manhuahot",
    "manhuakey",
    "manhuanext",
    "manhuaplus",
    "manhuaren",
    "manhuarmtl",
    "manhuascan",
    "manhuasite",
    "manhuatop",
    "manhuaus",
    "manhuazonghe",
    "manhwa_raw",
    "manhwa18",
    "manhwa18net",
    "manhwa68",
    "manhwaclub",
    "manhwaden",
    "manhwahub",
    "manhwanex",
    "manhwatoon",
    "manhwatop",
    "manhwazone",
    "manytoon",
    "multporn",
    "myhentaicomics",
    "myhentaigallery",
    "nhentai",
    "nhscans",
    "nightscans",
    "novelmic",
    "olympusbiblioteca",
    "omega_scans",
    "palcomix",
    "paradisescans",
    "pawmanga",
    "pururin",
    "readmanganato",
    "reaperscans",
    "resetscans",
    "rizzcomic",
    "s2manga",
    "sectscans",
    "setsuscans",
    "shibamanga",
    "simplyhentai",
    "skymanga",
    "svscomics",
    "tapas",
    "tappytoon",
    "templescan",
    "thunderscans",
    "toomics",
    "toonclash",
    "toongod",
    "toonily",
    "topmanhua",
    "topton",
    "tsumino",
    "utoon",
    "voidscans",
    "vymanga",
    "webtoons",
    "weebcentral",
    "wfwf",
    "xyzcomics",
    "yaoimangaonline",
    "zinmanga",
    "gingertoon",
]


def main() -> None:
    results: dict[str, list] = {
        "ok": [],
        "empty": [],
        "error": [],
        "excluded": [],
        "unknown": [],
    }
    for sid in SOURCES:
        if sid in EXCLUDED_CONNECTORS:
            results["excluded"].append(sid)
            continue
        try:
            connector = create_connector(sid)
            listing = connector.get_series_list(1)
            count = len(listing.items)
            if count:
                title = listing.items[0].title[:35]
                results["ok"].append((sid, count, title))
            else:
                results["empty"].append(sid)
        except Exception as exc:
            msg = str(exc).split("\n", maxsplit=1)[0][:100]
            if "Unknown source" in msg:
                results["unknown"].append((sid, msg))
            else:
                results["error"].append((sid, msg))

    print(f"OK {len(results['ok'])}")
    for row in results["ok"]:
        print(f"  {row}")
    print(f"EMPTY {len(results['empty'])}")
    print(f"  {results['empty']}")
    print(f"ERROR {len(results['error'])}")
    for row in results["error"]:
        print(f"  {row}")
    print(f"UNKNOWN {len(results['unknown'])}")
    for row in results["unknown"]:
        print(f"  {row}")
    print(f"EXCLUDED {results['excluded']}")


if __name__ == "__main__":
    main()
