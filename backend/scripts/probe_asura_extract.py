"""Extract API routes from AsuraScans HTML/JS."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://asurascans.com",
    "Referer": "https://asurascans.com/",
}

API_HEADERS = {**BROWSER_HEADERS, "Accept": "application/json, text/plain, */*"}

OUT = Path(__file__).parent / "asura_probe_out"
OUT.mkdir(exist_ok=True)


def fetch(url: str, *, api: bool = False) -> str:
    headers = API_HEADERS if api else BROWSER_HEADERS
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
    return response.text


def main() -> None:
    pages = {
        "home": "https://asurascans.com/",
        "browse": "https://asurascans.com/browse?page=1",
    }
    all_scripts: set[str] = set()
    for name, url in pages.items():
        html = fetch(url)
        (OUT / f"{name}.html").write_text(html, encoding="utf-8")
        print(name, "len", len(html))
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
        all_scripts.update(scripts)
        links = sorted(set(re.findall(r'href="(/[^"]+)"', html)))
        print(name, "links sample", [l for l in links if "series" in l or "comic" in l or "chapter" in l][:15])
        # astro island props / embedded json
        json_blobs = re.findall(r'type="application/json"[^>]*>(\{.*?\})</script>', html, re.S)
        print(name, "json blobs", len(json_blobs))
        for i, blob in enumerate(json_blobs[:3]):
            (OUT / f"{name}_json_{i}.json").write_text(blob, encoding="utf-8")
        slug_links = sorted(set(re.findall(r'/(?:series|comics)/[a-z0-9-]+', html)))
        print(name, "slug links", slug_links[:10])

    # fetch all astro chunks from home
    chunk_refs = set()
    for html_name in ("home", "browse"):
        html = (OUT / f"{html_name}.html").read_text(encoding="utf-8")
        chunk_refs.update(re.findall(r'/_astro/[^"\']+\.js', html))

    print("chunk refs", len(chunk_refs))
    api_paths: set[str] = set()
    for chunk in sorted(chunk_refs):
        url = "https://asurascans.com" + chunk
        try:
            js = fetch(url)
        except Exception as exc:
            print("chunk fail", chunk, exc)
            continue
        paths = re.findall(r'["\'](/[a-z][a-z0-9/_-]{2,80})["\']', js)
        for p in paths:
            if any(k in p for k in ("series", "chapter", "comic", "manga", "search", "browse", "page")):
                api_paths.add(p)
        full = re.findall(r'https://api\.asurascans\.com[^"\']*', js)
        api_paths.update(full)

    print("api paths from chunks:", sorted(api_paths)[:50])

    # brute force common API patterns
    candidates = []
    for prefix in ("", "/v1", "/v2", "/api"):
        for resource in ("comics", "series", "manga", "chapters", "browse"):
            for action in ("", "/list", "/search", "/latest", "/updates", "/trending", "/popular"):
                candidates.append(f"https://api.asurascans.com{prefix}/{resource}{action}?page=1")

    ok = []
    for url in candidates:
        try:
            response = httpx.get(url, headers=API_HEADERS, follow_redirects=True, timeout=15)
            if response.status_code != 404:
                ok.append((response.status_code, url, response.text[:200]))
        except Exception:
            pass
    print("non-404 api candidates:")
    for item in ok[:30]:
        print(item)


if __name__ == "__main__":
    main()
