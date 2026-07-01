"""Probe AsuraScans API routes."""

from __future__ import annotations

import json
import re

import httpx

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://asurascans.com",
    "Referer": "https://asurascans.com/",
}

API_BASE = "https://api.asurascans.com"


def try_get(path: str) -> None:
    url = f"{API_BASE}{path}"
    response = httpx.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=30)
    snippet = response.text[:300].replace("\n", " ")
    print(f"{response.status_code} {path} -> {snippet}")


def scan_home_js() -> None:
    response = httpx.get(
        "https://asurascans.com/",
        headers={**BROWSER_HEADERS, "Accept": "text/html"},
        follow_redirects=True,
        timeout=30,
    )
    html = response.text
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
    print("scripts", scripts[:10])
    for script in scripts[:5]:
        if not script.startswith("http"):
            script = "https://asurascans.com" + script
        js = httpx.get(script, headers=BROWSER_HEADERS, timeout=30).text
        paths = sorted(set(re.findall(r"/[a-z][a-z0-9/_-]{2,40}", js)))
        api_paths = [p for p in paths if "series" in p or "chapter" in p or "manga" in p]
        print("from", script.split("/")[-1], "api_paths", api_paths[:30])


if __name__ == "__main__":
    for path in [
        "/series/list?page=1",
        "/series/latest?page=1",
        "/series/search?name=solo&page=1",
        "/series/search?query=solo&page=1",
        "/series?name=solo&page=1",
        "/manga?page=1",
        "/comics?page=1",
        "/home",
        "/series/popular?page=1",
        "/series/trending?page=1",
        "/series/updates?page=1",
        "/v1/series?page=1",
        "/v1/series/list?page=1",
        "/v1/series/search?query=solo",
    ]:
        try_get(path)
    print("--- scan js ---")
    scan_home_js()
