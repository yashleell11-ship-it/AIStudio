#!/usr/bin/env python3
"""Live-probe every registered connector; write JSON results for pruning/fixes."""

from __future__ import annotations

import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from connectors.http.client import ConnectorHttpError  # noqa: E402
from connectors.madara.factory import madara_connector_classes  # noqa: E402
from connectors.madara.sites import MADARA_SITES  # noqa: E402
from connectors.registry import create_connector, list_installed_connectors  # noqa: E402

RESULTS_PATH = BACKEND.parent / "docs" / "connector_probe_results.json"
MAX_WORKERS = 6


@dataclass
class ProbeResult:
    source_id: str
    status: str  # LIVE | DEAD | ERROR
    items: int = 0
    mature: bool = False
    detail: str = ""
    sample_title: str = ""


def _probe_one(source_id: str) -> ProbeResult:
    mature = False
    try:
        for d in list_installed_connectors(include_mature=True):
            if d.source_type == source_id:
                mature = d.mature
                break
        connector = create_connector(source_id)
        listing = connector.get_series_list(1)
        count = len(listing.items)
        if count > 0:
            return ProbeResult(
                source_id=source_id,
                status="LIVE",
                items=count,
                mature=mature,
                sample_title=listing.items[0].title,
            )
        return ProbeResult(
            source_id=source_id,
            status="DEAD",
            mature=mature,
            detail="empty listing",
        )
    except ConnectorHttpError as exc:
        return ProbeResult(
            source_id=source_id,
            status="DEAD",
            mature=mature,
            detail=f"http {exc.status_code}: {exc}",
        )
    except Exception as exc:
        return ProbeResult(
            source_id=source_id,
            status="ERROR",
            mature=mature,
            detail=f"{type(exc).__name__}: {exc}",
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Probe registered connectors")
    parser.add_argument(
        "--retry-dead",
        action="store_true",
        help="Re-probe only sources marked DEAD in the last results file",
    )
    args = parser.parse_args()

    descriptors = list_installed_connectors(include_mature=True)
    source_ids = [d.source_type for d in descriptors if d.browsable]
    madara_ids = {cfg.source_id for cfg in MADARA_SITES}
    handcrafted = [sid for sid in source_ids if sid not in madara_ids]

    if args.retry_dead and RESULTS_PATH.exists():
        prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        dead_ids = {r["source_id"] for r in prev["results"] if r["status"] == "DEAD"}
        source_ids = [sid for sid in source_ids if sid in dead_ids]
        print(f"Retrying {len(source_ids)} previously-dead connectors...")

    print(f"Probing {len(source_ids)} browsable connectors ({len(madara_ids)} madara, {len(handcrafted)} hand-crafted)...")
    print(f"Workers: {MAX_WORKERS}", flush=True)

    results: list[ProbeResult] = []
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_probe_one, sid): sid for sid in source_ids}
        for future in as_completed(futures):
            sid = futures[future]
            done += 1
            try:
                result = future.result()
            except Exception:
                result = ProbeResult(
                    source_id=sid,
                    status="ERROR",
                    detail=traceback.format_exc()[-200:],
                )
            results.append(result)
            mark = "✓" if result.status == "LIVE" else "✗"
            print(
                f"[{done}/{len(source_ids)}] {mark} {result.source_id}: {result.status} "
                f"({result.items} items) {result.detail[:60]}",
                flush=True,
            )

    results.sort(key=lambda r: (r.status != "LIVE", r.source_id))
    live = [r for r in results if r.status == "LIVE"]
    dead = [r for r in results if r.status == "DEAD"]
    errors = [r for r in results if r.status == "ERROR"]

    payload = {
        "probed_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "live": len(live),
        "dead": len(dead),
        "error": len(errors),
        "results": [asdict(r) for r in results],
    }
    if args.retry_dead and RESULTS_PATH.exists():
        prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        merged = {r["source_id"]: r for r in prev["results"]}
        for r in results:
            merged[r.source_id] = asdict(r)
        merged_list = list(merged.values())
        live = [r for r in merged_list if r["status"] == "LIVE"]
        dead = [r for r in merged_list if r["status"] == "DEAD"]
        errors = [r for r in merged_list if r["status"] == "ERROR"]
        payload = {
            "probed_at": datetime.now(UTC).isoformat(),
            "total": len(merged_list),
            "live": len(live),
            "dead": len(dead),
            "error": len(errors),
            "results": merged_list,
        }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\n=== SUMMARY ===")
    print(f"LIVE:  {len(live)}")
    print(f"DEAD:  {len(dead)}")
    print(f"ERROR: {len(errors)}")
    print(f"Written: {RESULTS_PATH}")
    if live:
        print("\nLive sources:")
        for r in live:
            if isinstance(r, dict):
                print(f"  {r['source_id']}: {r['items']} ({r.get('sample_title', '')[:40]})")
            else:
                print(f"  {r.source_id}: {r.items} ({r.sample_title[:40]})")


if __name__ == "__main__":
    main()
