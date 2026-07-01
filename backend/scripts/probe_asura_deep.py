"""Deep probe of AsuraScans site structure."""

from __future__ import annotations

import json
import re

import httpx

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

API_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/json, text/plain, */*",
}


def probe_url(url: str, *, api: bool = False) -> None:
    headers = API_HEADERS if api else BROWSER_HEADERS
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
    text = response.text
    print(f"\n=== {response.url} status={response.status_code} len={len(text)} ===")
    if api or text.strip().startswith("{"):
        print(text[:800])
        return
    # embedded JSON
    for pattern in [
        r'"chapters"\s*:\s*(\[[\s\S]{0,200})',
        r'api\.asurascans\.com[^"\']+',
        r'/comics/[^"\']+',
        r'/series/[^"\']+',
        r'__NEXT_DATA__',
        r'window\.__[A-Z_]+__\s*=',
    ]:
        matches = re.findall(pattern, text)
        if matches:
            print(f"pattern {pattern!r}: {matches[:5]}")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', text)
    print("scripts:", scripts[:8])
    links = sorted(set(re.findall(r'href="(/[^"]+)"', text)))
    interesting = [l for l in links if any(k in l for k in ("comic", "series", "manga", "chapter"))]
    print("interesting links:", interesting[:20])


def scan_js_bundle(url: str) -> None:
    response = httpx.get(url, headers=BROWSER_HEADERS, timeout=30)
    js = response.text
    print(f"\n--- JS {url.split('/')[-1]} len={len(js)} ---")
    api_refs = sorted(set(re.findall(r'["\'](/[a-z][a-z0-9/_-]{2,60})["\']', js)))
    filtered = [
        p
        for p in api_refs
        if any(k in p for k in ("series", "chapter", "comic", "manga", "search", "page"))
    ]
    print("paths:", filtered[:40])
    hosts = sorted(set(re.findall(r'https://api\.[a-z0-9.-]+', js)))
    print("api hosts:", hosts)
    full_urls = sorted(set(re.findall(r'https://api\.asurascans\.com[^"\']*', js)))
    print("full api urls:", full_urls[:20])


if __name__ == "__main__":
    for url in [
        "https://asurascans.com/",
        "https://asurascans.com/comics",
        "https://asurascans.com/comics?page=1",
        "https://asurascans.com/browse",
        "https://asurascans.com/browse?page=1",
        "https://asurascans.com/search?q=solo",
        "https://asuracomic.net/series?page=1",
        "https://asuracomic.net/",
    ]:
        try:
            probe_url(url)
        except Exception as exc:
            print("FAIL", url, exc)

    for api_path in [
        "https://api.asurascans.com/comics?page=1",
        "https://api.asurascans.com/comics/list?page=1",
        "https://api.asurascans.com/comics/search?q=solo",
        "https://api.asurascans.com/comics/search?name=solo",
        "https://api.asurascans.com/comics/search?query=solo",
        "https://api.asurascans.com/comics/latest?page=1",
        "https://api.asurascans.com/comics/updates?page=1",
        "https://api.asurascans.com/comics/trending",
        "https://api.asurascans.com/comics/popular",
        "https://api.asurascans.com/auth/me",
        "https://api.asurascans.com/promotion",
        "https://api.asurascans.com/health",
        "https://api.asurascans.com/swagger/index.html",
        "https://api.asurascans.com/docs",
    ]:
        try:
            probe_url(api_path, api=True)
        except Exception as exc:
            print("API FAIL", api_path, exc)

    home = httpx.get("https://asurascans.com/", headers=BROWSER_HEADERS, timeout=30).text
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', home)
    for script in scripts[:6]:
        if script.startswith("/"):
            scan_js_bundle("https://asurascans.com" + script)
