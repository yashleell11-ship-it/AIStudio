#!/usr/bin/env python3
"""HTTP probe every catalog domain; classify Madara vs custom vs dead.

Runs before connector-level probes to detect sites that need dedicated
connectors instead of the Madara factory.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from connectors.catalog import HANDCRAFTED_CONNECTORS, MADARA_CATALOG  # noqa: E402

RESULTS_PATH = BACKEND.parent / "docs" / "catalog_domain_probe.json"
CONNECTOR_RESULTS = BACKEND.parent / "docs" / "connector_probe_results.json"
MAX_WORKERS = 8
TIMEOUT = 20.0

HANDCRAFTED = HANDCRAFTED_CONNECTORS
EXCLUDED = frozenset({"comick"})

MADARA_MARKERS = (
    "wp-manga",
    "page-item-detail",
    "c-tabs-item__content",
    "madara",
    "wp-manga-chapter",
)
SPA_MARKERS = ("__NEXT_DATA__", "_next/static", "react-root", "ng-version")
API_MARKERS = ('"/api/', "'/api/", "application/json")


@dataclass
class DomainProbeResult:
    source_id: str
    domain: str
    mature: bool
    url_segment: str
    classification: str  # TRUE_MADARA | CUSTOM_NEEDED | DEAD | UNREACHABLE | HANDCRAFTED
    http_status: int | None = None
    listing_cards: int = 0
    markers: str = ""
    detail: str = ""
    strikes: int = 0


def _fetch(base_url: str, path: str, *, use_cf: bool) -> tuple[int | None, str, str]:
    """Return (status, body snippet, error detail)."""
    headers = {"Accept": "text/html,application/xhtml+xml"}
    try:
        if use_cf:
            from connectors.http.cf_client import CfSyncHttpClient

            client = CfSyncHttpClient(
                base_url,
                headers=headers,
                impersonate="chrome131",
                timeout=TIMEOUT,
            )
            try:
                text = client.get_text(path)
            finally:
                client.close()
            return 200, text[:120_000], ""
        import httpx

        resp = httpx.get(
            f"{base_url.rstrip('/')}/{path.lstrip('/')}",
            headers=headers,
            follow_redirects=True,
            timeout=TIMEOUT,
        )
        text = resp.text[:120_000] if resp.text else ""
        return resp.status_code, text, ""
    except Exception as exc:
        from connectors.http.client import ConnectorHttpError

        if isinstance(exc, ConnectorHttpError):
            return exc.status_code, "", str(exc)[:200]
        return None, "", f"{type(exc).__name__}: {exc}"[:200]


def _count_listing_cards(html: str, url_segment: str) -> int:
    pattern = re.compile(
        rf'class="page-item-detail[^"]*"[^>]*>.*?/{url_segment}/[a-z0-9-]+/',
        re.I | re.S,
    )
    return len(pattern.findall(html))


def _detect_markers(html: str) -> list[str]:
    lower = html.lower()
    found: list[str] = []
    for marker in MADARA_MARKERS:
        if marker in lower:
            found.append(f"madara:{marker}")
    for marker in SPA_MARKERS:
        if marker.lower() in lower:
            found.append(f"spa:{marker}")
    for marker in API_MARKERS:
        if marker in html:
            found.append(f"api:{marker}")
    return found


def _load_strikes() -> dict[str, int]:
    strikes: dict[str, int] = {}
    if CONNECTOR_RESULTS.exists():
        data = json.loads(CONNECTOR_RESULTS.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            if row.get("status") in ("DEAD", "ERROR"):
                strikes[row["source_id"]] = strikes.get(row["source_id"], 0) + 1
    if RESULTS_PATH.exists():
        data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            if row.get("classification") in ("DEAD", "UNREACHABLE"):
                strikes[row["source_id"]] = strikes.get(row["source_id"], 0) + 1
    return strikes


def _probe_site(
    source_id: str,
    domain: str,
    *,
    mature: bool,
    url_segment: str,
    use_cf: bool,
    strikes: dict[str, int],
) -> DomainProbeResult:
    if source_id in HANDCRAFTED:
        return DomainProbeResult(
            source_id=source_id,
            domain=domain,
            mature=mature,
            url_segment=url_segment,
            classification="HANDCRAFTED",
            detail="registered custom connector",
        )

    base = f"https://{domain}"
    status, body, err = _fetch(base, f"/{url_segment}/", use_cf=use_cf)
    if not body and (status is None or status >= 400):
        home_status, home_body, home_err = _fetch(base, "/", use_cf=use_cf)
        if home_body:
            status, body, err = home_status, home_body, home_err
        elif status is None:
            status, err = home_status, home_err or err

    if status is None:
        return DomainProbeResult(
            source_id=source_id,
            domain=domain,
            mature=mature,
            url_segment=url_segment,
            classification="UNREACHABLE",
            detail=err[:200],
            strikes=strikes.get(source_id, 0) + 1,
        )

    if status >= 400:
        return DomainProbeResult(
            source_id=source_id,
            domain=domain,
            mature=mature,
            url_segment=url_segment,
            classification="DEAD",
            http_status=status,
            detail=f"http {status}",
            strikes=strikes.get(source_id, 0) + 1,
        )

    markers = _detect_markers(body)
    cards = _count_listing_cards(body, url_segment)

    madara_hits = [m for m in markers if m.startswith("madara:")]
    spa_hits = [m for m in markers if m.startswith("spa:")]
    api_hits = [m for m in markers if m.startswith("api:")]

    if madara_hits and cards >= 3:
        classification = "TRUE_MADARA"
    elif madara_hits and cards > 0:
        classification = "TRUE_MADARA"
    elif api_hits or spa_hits:
        classification = "CUSTOM_NEEDED"
    elif cards >= 3:
        classification = "CUSTOM_NEEDED"
    elif len(body) < 500:
        classification = "DEAD"
    else:
        classification = "CUSTOM_NEEDED"

    return DomainProbeResult(
        source_id=source_id,
        domain=domain,
        mature=mature,
        url_segment=url_segment,
        classification=classification,
        http_status=status,
        listing_cards=cards,
        markers=", ".join(markers[:6]),
        detail="" if classification != "DEAD" else "no recognizable listing",
        strikes=strikes.get(source_id, 0) + (1 if classification in ("DEAD", "UNREACHABLE") else 0),
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Probe catalog domains for structure")
    parser.add_argument(
        "--ids",
        nargs="*",
        help="Probe only these source_ids (default: full Madara catalog)",
    )
    parser.add_argument(
        "--retry-dead",
        action="store_true",
        help="Only re-probe sources classified DEAD/UNREACHABLE last run",
    )
    args = parser.parse_args()

    strikes = _load_strikes()
    configs = list(MADARA_CATALOG)

    if args.ids:
        wanted = set(args.ids)
        configs = [c for c in configs if c.source_id in wanted]
    elif args.retry_dead and RESULTS_PATH.exists():
        prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        dead_ids = {
            r["source_id"]
            for r in prev["results"]
            if r["classification"] in ("DEAD", "UNREACHABLE")
        }
        configs = [c for c in configs if c.source_id in dead_ids]

    print(f"Domain-probing {len(configs)} catalog entries...", flush=True)

    results: list[DomainProbeResult] = []
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _probe_site,
                cfg.source_id,
                cfg.site_host,
                mature=cfg.mature,
                url_segment=cfg.url_segment,
                use_cf=cfg.use_cf,
                strikes=strikes,
            ): cfg.source_id
            for cfg in configs
        }
        for future in as_completed(futures):
            sid = futures[future]
            done += 1
            result = future.result()
            results.append(result)
            print(
                f"[{done}/{len(configs)}] {result.classification:14} {sid:22} "
                f"cards={result.listing_cards} {result.detail[:40]}",
                flush=True,
            )

    # Include handcrafted rows for a complete status table
    for sid in sorted(HANDCRAFTED):
        if not any(r.source_id == sid for r in results):
            results.append(
                DomainProbeResult(
                    source_id=sid,
                    domain="(custom)",
                    mature=sid in {"toonily"},
                    url_segment="n/a",
                    classification="HANDCRAFTED",
                    detail="registered custom connector",
                )
            )

    results.sort(key=lambda r: (r.classification, r.source_id))

    counts: dict[str, int] = {}
    for r in results:
        counts[r.classification] = counts.get(r.classification, 0) + 1

    payload = {
        "probed_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "counts": counts,
        "three_strike_dead": [
            r.source_id for r in results if r.strikes >= 3 and r.classification in ("DEAD", "UNREACHABLE")
        ],
        "results": [asdict(r) for r in results],
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== DOMAIN PROBE SUMMARY ===")
    for label, count in sorted(counts.items()):
        print(f"  {label}: {count}")
    print(f"  3-strike skip list: {len(payload['three_strike_dead'])}")
    print(f"Written: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
