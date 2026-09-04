#!/usr/bin/env python3
"""Measure what the reader actually waits for: page image bytes.

The reader's cost per chapter is dominated by the image proxy, not by the
HTML parsing the e2e check times. This isolates one question the e2e grid
cannot answer: how much of that time is TLS/TCP setup that a pooled client
would not pay.

``BrowseService._fetch_url`` calls the module-level ``httpx.stream(...)``,
which builds and discards an entire ``httpx.Client`` per call -- a fresh DNS
lookup, TCP connect and TLS handshake for every single page image. Mode B
issues the byte-identical requests through one pooled, keep-alive client so
the delta is purely connection reuse.

Run it inside the production container so the egress IP, TLS stack and CDN
routing match what a real read hits:

    docker exec -w /app manhwamaniacs-backend \
        python /app/scripts/bench_image_proxy.py --source mangadex --pages 8
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import httpx  # noqa: E402

from connectors.registry import create_connector  # noqa: E402


def _resolve_pages(source: str, want: int) -> tuple[object, list]:
    """Walk browse -> detail -> chapters -> pages for the first readable series."""
    conn = create_connector(source)
    listing = conn.get_series_list(1)
    items = list(getattr(listing, "items", []) or [])
    for item in items[:5]:
        try:
            chapters = list(conn.get_chapters(item.id) or [])
        except Exception:  # noqa: BLE001
            continue
        if not chapters:
            continue
        try:
            pages = list(conn.get_chapter_pages(chapters[0].id) or [])
        except Exception:  # noqa: BLE001
            continue
        pages = [p for p in pages if getattr(p, "remote_url", None)]
        if pages:
            return conn, pages[:want]
    return conn, []


def _fetch_per_request(url: str, headers: dict[str, str]) -> int:
    """Today's path: a brand-new client (and TLS handshake) per image."""
    with httpx.stream(
        "GET", url, timeout=30.0, follow_redirects=False, headers=headers
    ) as response:
        response.raise_for_status()
        return sum(len(chunk) for chunk in response.iter_bytes())


def _fetch_pooled(client: httpx.Client, url: str, headers: dict[str, str]) -> int:
    with client.stream(
        "GET", url, timeout=30.0, follow_redirects=False, headers=headers
    ) as response:
        response.raise_for_status()
        return sum(len(chunk) for chunk in response.iter_bytes())


def _run(label: str, fetch, urls: list[str], headers: dict[str, str]) -> dict:
    per_image: list[float] = []
    errors = 0
    total_bytes = 0
    t0 = time.monotonic()
    for url in urls:
        t = time.monotonic()
        try:
            total_bytes += fetch(url)
        except Exception:  # noqa: BLE001
            errors += 1
        per_image.append(time.monotonic() - t)
    wall = time.monotonic() - t0
    return {
        "label": label,
        "images": len(urls),
        "errors": errors,
        "bytes": total_bytes,
        "wall_secs": round(wall, 2),
        "mean_ms": round(1000 * statistics.mean(per_image), 1) if per_image else 0.0,
        "median_ms": round(1000 * statistics.median(per_image), 1) if per_image else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    conn, pages = _resolve_pages(args.source, args.pages)
    if not pages:
        print(json.dumps({"source": args.source, "error": "no readable pages"}))
        raise SystemExit(1)

    headers = conn.image_fetch_headers()
    urls = [p.remote_url for p in pages]

    # Warm DNS + any CDN-side cold start once so the comparison is not just
    # "whoever went first paid for the lookup".
    try:
        _fetch_per_request(urls[0], headers)
    except Exception:  # noqa: BLE001
        pass

    a = _run("per-request client (today)", lambda u: _fetch_per_request(u, headers),
             urls, headers)
    with httpx.Client(
        timeout=30.0,
        follow_redirects=False,
        limits=httpx.Limits(max_keepalive_connections=32, max_connections=64),
    ) as client:
        b = _run("pooled keep-alive client", lambda u: _fetch_pooled(client, u, headers),
                 urls, headers)

    speedup = (a["wall_secs"] / b["wall_secs"]) if b["wall_secs"] else 0.0
    payload = {
        "source": args.source,
        "sampled_pages": len(urls),
        "per_request": a,
        "pooled": b,
        "wall_speedup": round(speedup, 2),
        "saved_ms_per_image": round(a["mean_ms"] - b["mean_ms"], 1),
    }
    print(json.dumps(payload, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
