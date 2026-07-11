"""Fetch live Madara-theme HTML fixtures for connector development."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from connectors.http.cf_client import CfSyncHttpClient, is_cloudflare_challenge  # noqa: E402
from connectors.http.client import ConnectorHttpError  # noqa: E402
from connectors.madara.config import MadaraSiteConfig  # noqa: E402
from connectors.madara.mappers import MadaraHtml  # noqa: E402

FIXTURES_ROOT = BACKEND / "tests" / "fixtures" / "madara"
STATUS_DOC = BACKEND.parents[0] / "docs" / "CONNECTOR_STATUS.md"

BROWSE_CANDIDATES = (
    "/manga/",
    "/webtoons/",
    "/serie/",
    "/comics/",
    "/type/manga",
    "/type/manga/",
    "/",
)

SEARCH_PATH = "/"
SEARCH_PARAMS = {"s": "solo", "post_type": "wp-manga"}


@dataclass
class SiteSpec:
    source_id: str
    base_url: str
    browse_path: str | None = None


SITES: list[SiteSpec] = [
    SiteSpec("natomanga", "https://natomanga.com", "/manga/"),
    SiteSpec("readmanganato", "https://readmanganato.com", "/manga/"),
    SiteSpec("mangabat", "https://mangabat.com", "/manga/"),
    SiteSpec("mangafire", "https://mangafire.to"),
    SiteSpec("zinmanga", "https://zinmanga.com"),
    SiteSpec("manhuaplus", "https://manhuaplus.com"),
    SiteSpec("flamecomics", "https://flamecomics.xyz"),
]


def is_madara_html(html: str) -> bool:
    lowered = html.lower()
    return "page-item-detail" in lowered or "wp-manga" in lowered


def fetch_text(client: CfSyncHttpClient, path: str, *, params: dict | None = None) -> tuple[int, str]:
    """Return (status_code, html). status_code is 0 on transport/CF failure."""
    url = client._resolve_url(path)  # noqa: SLF001 — script-only probe
    last_status = 0
    last_html = ""

    for attempt in range(client._max_retries):  # noqa: SLF001
        client._rate_limit()  # noqa: SLF001
        try:
            response = client._session.get(  # noqa: SLF001
                url,
                params=params,
                headers=client._headers,  # noqa: SLF001
                timeout=client._timeout,  # noqa: SLF001
                allow_redirects=True,
            )
            last_status = response.status_code
            last_html = response.text
            if response.status_code >= 400:
                if attempt + 1 < client._max_retries:  # noqa: SLF001
                    continue
                return last_status, last_html
            if is_cloudflare_challenge(last_html):
                last_status = 403
                if attempt + 1 < client._max_retries:  # noqa: SLF001
                    continue
                return last_status, last_html
            return last_status, last_html
        except OSError:
            last_status = 0
            if attempt + 1 >= client._max_retries:
                break
    return last_status, last_html


def discover_browse_path(client: CfSyncHttpClient) -> tuple[str | None, int, str]:
    best: tuple[str | None, int, str] = (None, 0, "")
    for candidate in BROWSE_CANDIDATES:
        status, html = fetch_text(client, candidate)
        if status == 200 and is_madara_html(html) and "page-item-detail" in html.lower():
            return candidate, status, html
        if status == 200 and is_madara_html(html):
            best = (candidate, status, html)
    return best


def page2_path(browse_path: str) -> str:
    trimmed = browse_path.rstrip("/")
    if trimmed.endswith("/page"):
        return f"{trimmed}/2/"
    return f"{trimmed}/page/2/"


def write_status_rows(rows: list[tuple[str, str, str, str]]) -> None:
    lines = [
        "# Connector Status",
        "",
        "Live probe results for Madara-theme source candidates (CfSyncHttpClient, chrome131, 3 retries).",
        "",
        "| Source ID | URL | Status | HTTP |",
        "|-----------|-----|--------|------|",
    ]
    for source_id, url, status, http in rows:
        lines.append(f"| `{source_id}` | {url} | **{status}** | {http} |")
    lines.append("")
    STATUS_DOC.parent.mkdir(parents=True, exist_ok=True)
    STATUS_DOC.write_text("\n".join(lines), encoding="utf-8")


def process_site(spec: SiteSpec) -> tuple[str | None, tuple[str, str, str, str]]:
    client = CfSyncHttpClient(spec.base_url, impersonate="chrome131", max_retries=3)
    try:
        if spec.browse_path:
            browse_path = spec.browse_path
            status, browse_html = fetch_text(client, browse_path)
        else:
            browse_path, status, browse_html = discover_browse_path(client)

        if status != 200 or not is_madara_html(browse_html):
            http = str(status) if status else "error"
            return None, (spec.source_id, spec.base_url, "DEAD", http)

        config = MadaraSiteConfig(
            source_id=spec.source_id,
            display_name=spec.source_id.replace("_", " ").title(),
            base_url=spec.base_url.rstrip("/"),
        )
        parser = MadaraHtml(config)

        out_dir = FIXTURES_ROOT / spec.source_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "browse_latest.html").write_text(browse_html, encoding="utf-8")

        page2 = page2_path(browse_path)
        p2_status, page2_html = fetch_text(client, page2)
        if p2_status == 200 and is_madara_html(page2_html):
            (out_dir / "browse_page2.html").write_text(page2_html, encoding="utf-8")

        search_status, search_html = fetch_text(client, SEARCH_PATH, params=SEARCH_PARAMS)
        if search_status == 200 and is_madara_html(search_html):
            (out_dir / "search.html").write_text(search_html, encoding="utf-8")

        listing = parser.parse_series_list(browse_html, page=1)
        if not listing.items:
            return None, (spec.source_id, spec.base_url, "DEAD", f"{status} (no series)")

        series = listing.items[0]
        detail_path = parser.series_id_to_path(series.id)
        detail_status, detail_html = fetch_text(client, detail_path)
        if detail_status != 200 or not is_madara_html(detail_html):
            return None, (spec.source_id, spec.base_url, "DEAD", f"{detail_status} (detail)")

        (out_dir / "series_detail.html").write_text(detail_html, encoding="utf-8")

        chapters = parser.parse_chapters(detail_html, series.id)
        if not chapters:
            chapter_match = re.search(
                rf'href="https?://[^"]+/{config.url_segment}/([^"]+/chapter-[^"]+)"',
                detail_html,
                re.I,
            )
            if chapter_match:
                chapter_path = f"/{config.url_segment}/{chapter_match.group(1)}/"
            else:
                return None, (spec.source_id, spec.base_url, "DEAD", f"{detail_status} (no chapters)")
        else:
            chapter_path = parser.chapter_id_to_path(chapters[-1].id)

        reader_status, reader_html = fetch_text(client, chapter_path)
        if reader_status != 200 or not is_madara_html(reader_html):
            return None, (spec.source_id, spec.base_url, "DEAD", f"{reader_status} (reader)")

        (out_dir / "chapter_reader.html").write_text(reader_html, encoding="utf-8")
        return spec.source_id, (spec.source_id, spec.base_url, "ALIVE", str(status))
    finally:
        client.close()


def main() -> None:
    saved: list[str] = []
    dead: list[str] = []
    rows: list[tuple[str, str, str, str]] = []

    for spec in SITES:
        print(f"Fetching {spec.source_id} ({spec.base_url})...", flush=True)
        source_id, row = process_site(spec)
        rows.append(row)
        if source_id:
            saved.append(source_id)
            print(f"  OK -> {FIXTURES_ROOT / source_id}", flush=True)
        else:
            dead.append(spec.source_id)
            print(f"  DEAD ({row[3]})", flush=True)

    write_status_rows(rows)
    print(f"\nSaved fixtures: {saved}")
    print(f"Dead sites: {dead}")
    print(f"Status doc: {STATUS_DOC}")


if __name__ == "__main__":
    main()
