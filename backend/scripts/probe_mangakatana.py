"""Probe MangaKatana HTML structure for connector development."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx

BASE = "https://mangakatana.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def fetch(path: str, *, params: dict | None = None) -> str:
    response = httpx.get(
        urljoin(BASE, path),
        headers=HEADERS,
        params=params,
        follow_redirects=True,
        timeout=60,
    )
    print(f"GET {path} params={params} -> {response.status_code} len={len(response.text)}")
    response.raise_for_status()
    return response.text


def parse_book_list(html: str) -> list[tuple[str, str]]:
    block = re.search(r'<div id="book_list">(.*?)</div>\s*<div class="uk-margin-large-top">', html, re.S)
    if not block:
        return []
    content = block.group(1)
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r'<div class="item">.*?<h3 class="title">\s*<a href="https?://[^"]+/manga/([^"/]+)"[^>]*>([^<]+)</a>',
        content,
        re.S | re.I,
    ):
        series_id, title = match.group(1), match.group(2).strip()
        if series_id in seen:
            continue
        seen.add(series_id)
        items.append((series_id, title))
    return items


def parse_chapters(html: str, series_id: str) -> list[tuple[str, str]]:
    block = re.search(r'<div class="chapters">(.*?)</div>\s*<div class="uk-margin">', html, re.S | re.I)
    if not block:
        return []
    items: list[tuple[str, str]] = []
    for match in re.finditer(
        r'<div class="chapter[^"]*">\s*<a href="https?://[^"]+/manga/([^"]+)"[^>]*>([^<]+)</a>',
        block.group(1),
        re.I,
    ):
        chapter_id, title = match.group(1), match.group(2).strip()
        if not chapter_id.startswith(series_id + "/"):
            continue
        items.append((chapter_id, title))
    return items


def extract_page_urls(html: str) -> list[str]:
    arrays = re.findall(r"var\s+\w+\s*=\s*\[(.*?)\];", html, re.S)
    urls: list[str] = []
    for body in arrays:
        found = re.findall(r"'(https?://[^']+)'", body)
        if len(found) >= 2:
            urls = found
            break
    return urls


def main() -> None:
    html1 = fetch("/manga/page/1", params={"filter": 1})
    html2 = fetch("/manga/page/2", params={"filter": 1})
    items1 = parse_book_list(html1)
    items2 = parse_book_list(html2)
    print("page1", len(items1), items1[:3])
    print("page2", len(items2), items2[:3])
    print("overlap", len(set(items1) & set(items2)))

    last_page = re.findall(r'uk-pagination.*?href="[^"]+/manga/page/(\d+)', html1, re.S)
    print("pagination pages", sorted(set(int(x) for x in last_page))[-5:])

    for filt in [1, "popular", "latest", "rating"]:
        html = fetch("/manga/page/1", params={"filter": filt})
        print("filter", filt, parse_book_list(html)[:2])

    # search in site header
    for needle in ['name="search"', 'id="search"', 'autocomplete', '/manga/page/1?search']:
        print("search needle", needle, needle in html1)

    detail = fetch("/manga/aishiteru-uso-dakedo.10797")
    chapters = parse_chapters(detail, "aishiteru-uso-dakedo.10797")
    print("chapters", chapters)

    chapter = fetch("/manga/aishiteru-uso-dakedo.10797/c1")
    imgs = extract_page_urls(chapter)
    print("imgs", len(imgs), imgs[:3])

    for params in [{"search": "solo leveling"}, {"search": "tower"}]:
        html = fetch("/manga/page/1", params=params)
        items = parse_book_list(html)
        print("search params", params, len(items), [t for _, t in items[:5]])


if __name__ == "__main__":
    main()
