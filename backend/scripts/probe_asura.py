"""Probe AsuraScans site structure."""

from __future__ import annotations

import json
import re
import sys

import httpx

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url: str) -> httpx.Response:
    return httpx.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=30)


def probe_html(url: str) -> None:
    response = fetch(url)
    html = response.text
    print("URL", response.url, "status", response.status_code, "len", len(html))
    apis = sorted(set(re.findall(r"https://[a-z0-9.-]+/api[^\s\"'<>]+", html)))
    print("api urls", apis[:20])
    hosts = sorted(set(re.findall(r"https://api\.[a-z0-9.-]+", html)))
    print("api hosts", hosts[:10])
    if "Nano Machine" in html:
        print("contains Nano Machine")
    slugs = sorted(set(re.findall(r"/series/[a-z0-9-]+", html)))
    print("slug paths", slugs[:10])


def probe_api(url: str) -> None:
    response = httpx.get(
        url,
        headers={
            **BROWSER_HEADERS,
            "Accept": "application/json",
        },
        follow_redirects=True,
        timeout=30,
    )
    print("API", url, "status", response.status_code)
    text = response.text[:500]
    print(text)


if __name__ == "__main__":
    probe_html("https://asurascans.com/series?page=1")
    probe_html("https://asurascans.com/series?name=solo")
    for candidate in [
        "https://api.asurascans.com/series?page=1",
        "https://api.asurascans.com/v1/series?page=1",
        "https://asurascans.com/api/series?page=1",
        "https://gg.asuracomic.net/api/series?page=1",
    ]:
        try:
            probe_api(candidate)
        except Exception as exc:
            print("API fail", candidate, exc)
