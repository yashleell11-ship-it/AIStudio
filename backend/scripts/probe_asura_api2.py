"""Probe confirmed AsuraScans API routes."""

from __future__ import annotations

import json
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://asurascans.com",
    "Referer": "https://asurascans.com/",
}

BASE = "https://api.asurascans.com"


def get(path: str) -> None:
    url = f"{BASE}{path}"
    response = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    text = response.text
    print(f"\n{response.status_code} {path}")
    try:
        payload = response.json()
        print(json.dumps(payload, indent=2)[:2500])
    except Exception:
        print(text[:500])


if __name__ == "__main__":
    for path in [
        "/api/series?page=1",
        "/api/series?page=2",
        "/api/series?search=solo",
        "/api/series?name=solo",
        "/api/series?query=solo",
        "/api/series?q=solo",
        "/api/series/search?q=solo",
        "/api/series/search?query=solo",
        "/api/series/search?name=solo",
        "/api/trending/home?limit=10",
        "/api/trending/daily?limit=10",
        "/api/series/return-of-the-mount-hua-sect-30e93729",
        "/api/comics/return-of-the-mount-hua-sect-30e93729",
        "/api/series/return-of-the-mount-hua-sect",
        "/api/series/slug/return-of-the-mount-hua-sect-30e93729",
    ]:
        get(path)

    # list one series from page 1 for follow-up
    listing = httpx.get(f"{BASE}/api/series?page=1", headers=HEADERS, timeout=30).json()
    first = listing["data"][0]
    series_id = first["id"]
    slug = first["slug"]
    print("\nFIRST SERIES", series_id, slug, first.get("title"))

    for path in [
        f"/api/series/{series_id}",
        f"/api/series/{slug}",
        f"/api/series/{slug}-30e93729",
        f"/api/series/{series_id}/chapters",
        f"/api/chapters?series_id={series_id}",
        f"/api/series/{series_id}/chapter",
    ]:
        get(path)

    # try chapter from home page slug
    chapter_paths = [
        "/api/chapters/90",
        "/api/chapter/90",
        "/api/comics/breakers-30e93729/chapter/91",
        "/api/series/breakers-30e93729/chapters/91",
    ]
    for path in chapter_paths:
        get(path)
