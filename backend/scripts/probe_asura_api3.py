"""Probe AsuraScans chapters and pagination."""

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
    "Origin": "https://asurascans.com",
    "Referer": "https://asurascans.com/",
}

BASE = "https://api.asurascans.com"


def dump(path: str) -> dict:
    response = httpx.get(f"{BASE}{path}", headers=HEADERS, timeout=30)
    print(f"\n{response.status_code} {path}")
    payload = response.json()
    print(json.dumps(payload, indent=2)[:4000])
    return payload


if __name__ == "__main__":
    listing = dump("/api/series?page=1")
    print("TOP KEYS", listing.keys())
    if "meta" in listing:
        print("META", listing["meta"])
    if "pagination" in listing:
        print("PAGINATION", listing["pagination"])

    for path in [
        "/api/series/return-of-the-mount-hua-sect/chapters",
        "/api/series/return-of-the-mount-hua-sect-30e93729/chapters",
        "/api/series/breakers-30e93729/chapters",
    ]:
        dump(path)

    detail = dump("/api/series/return-of-the-mount-hua-sect-30e93729")
    print("DETAIL KEYS", detail.keys())

    chapter = dump("/api/series/return-of-the-mount-hua-sect-30e93729/chapters/169")
    chap = chapter.get("data", {}).get("chapter", {})
    print("CHAPTER ID", chap.get("id"), "NUMBER", chap.get("number"))

    for path in [
        f"/api/chapters/{chap.get('id')}",
        f"/api/series/return-of-the-mount-hua-sect-30e93729/chapters/{chap.get('id')}",
        f"/api/series/return-of-the-mount-hua-sect-30e93729/chapters/chapter-169",
    ]:
        dump(path)
