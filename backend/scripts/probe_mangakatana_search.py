"""Probe MangaKatana GET search."""

from __future__ import annotations

import re

import httpx

HEADERS = {"User-Agent": "Mozilla/5.0"}

for params in [
    {"search": "solo leveling", "search_by": "m_name"},
    {"search": "tower", "search_by": "m_name"},
    {"search": "one piece", "search_by": "m_name"},
]:
    r = httpx.get("https://mangakatana.com/", params=params, headers=HEADERS, timeout=60)
    ids = re.findall(r'/manga/([a-z0-9.-]+\.\d+)"', r.text, re.I)
    uniq = []
    seen = set()
    for item in ids:
        if "/" in item or item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    titles = re.findall(
        r'<h3 class="title">\s*<a href="https?://[^"]+/manga/[^"]+"[^>]*>([^<]+)</a>',
        r.text,
        re.I,
    )
    print(params, "status", r.status_code, "ids", len(uniq), uniq[:5])
    print(" titles", titles[:5])
