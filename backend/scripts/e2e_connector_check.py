#!/usr/bin/env python3
"""Live end-to-end connector check.

For every registered connector, exercise the full read path a user hits:

    browse  -> get_series_list(1)
    detail  -> get_series(first.id)
    chapters-> get_chapters(first.id)          ("chapters inside the series")
    pages   -> get_chapter_pages(first chapter) ("pages inside the chapter")

Records a per-stage PASS/FAIL + timing + error so we can print a tick-mark
table of what actually works live. Runs connectors concurrently with a hard
per-connector timeout so dead/slow sites never hang the run.

Usage:
    ./.venv/bin/python scripts/e2e_connector_check.py            # all browsable
    ./.venv/bin/python scripts/e2e_connector_check.py --mature   # include mature
    ./.venv/bin/python scripts/e2e_connector_check.py --only id1,id2
    ./.venv/bin/python scripts/e2e_connector_check.py --workers 8 --timeout 30
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from connectors.registry import create_connector, list_installed_connectors  # noqa: E402

STAGES = ("browse", "detail", "chapters", "pages")


def _first_id(items) -> str | None:
    for it in items:
        sid = getattr(it, "id", None)
        if sid:
            return sid
    return None


def check_one(source_type: str) -> dict:
    result = {
        "source_id": source_type,
        "browse": "-",
        "detail": "-",
        "chapters": "-",
        "pages": "-",
        "series_sample": "",
        "n_series": 0,
        "n_chapters": 0,
        "n_pages": 0,
        "error": "",
        "ok": False,
        "secs": 0.0,
    }
    t0 = time.monotonic()
    try:
        conn = create_connector(source_type)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"create: {type(exc).__name__}: {exc}"[:200]
        result["secs"] = round(time.monotonic() - t0, 1)
        return result

    # browse
    try:
        listing = conn.get_series_list(1)
        items = list(getattr(listing, "items", []) or [])
        result["n_series"] = len(items)
        if not items:
            result["browse"] = "FAIL"
            result["error"] = "browse returned 0 series"
            result["secs"] = round(time.monotonic() - t0, 1)
            return result
        result["browse"] = "PASS"
        first = items[0]
        result["series_sample"] = (getattr(first, "title", "") or "")[:48]
    except Exception as exc:  # noqa: BLE001
        result["browse"] = "FAIL"
        result["error"] = f"browse: {type(exc).__name__}: {exc}"[:200]
        result["secs"] = round(time.monotonic() - t0, 1)
        return result

    # Walk detail->chapters->pages for up to a few browsed series: a single
    # title can be a source-data anomaly (e.g. a licensed/delisted series with
    # no readable chapters), so try the next series before declaring failure.
    # We keep the best (deepest-reaching) attempt.
    candidate_ids = [sid for sid in (_first_id([it]) for it in items[:5]) if sid]
    best = {"detail": "FAIL", "chapters": "FAIL", "pages": "-",
            "n_chapters": 0, "n_pages": 0, "sample": result["series_sample"],
            "error": "", "depth": -1}

    def _depth(d: dict) -> int:
        score = 0
        if d["detail"] == "PASS":
            score = 1
        if d["chapters"] == "PASS":
            score = 2
        if d["pages"] == "PASS":
            score = 3
        return score

    for series_id in candidate_ids:
        attempt = {"detail": "FAIL", "chapters": "FAIL", "pages": "-",
                   "n_chapters": 0, "n_pages": 0,
                   "sample": result["series_sample"], "error": "", "depth": -1}
        chapter_id = None
        try:
            series = conn.get_series(series_id)
            attempt["detail"] = "PASS" if series is not None else "FAIL"
            if series is None:
                attempt["error"] = "detail returned None"
            elif getattr(series, "title", None):
                attempt["sample"] = series.title[:48]
        except Exception as exc:  # noqa: BLE001
            attempt["error"] = f"detail: {type(exc).__name__}: {exc}"[:200]
        try:
            chapters = list(conn.get_chapters(series_id) or [])
            attempt["n_chapters"] = len(chapters)
            attempt["chapters"] = "PASS" if chapters else "FAIL"
            if not chapters and not attempt["error"]:
                attempt["error"] = "0 chapters"
            if chapters:
                chapter_id = getattr(chapters[0], "id", None)
        except Exception as exc:  # noqa: BLE001
            attempt["error"] = attempt["error"] or f"chapters: {type(exc).__name__}: {exc}"[:200]
        if chapter_id is not None:
            try:
                pages = list(conn.get_chapter_pages(chapter_id) or [])
                attempt["n_pages"] = len(pages)
                has_url = bool(pages) and bool(getattr(pages[0], "remote_url", None))
                attempt["pages"] = "PASS" if has_url else "FAIL"
                if not has_url and not attempt["error"]:
                    attempt["error"] = "0 pages / no image url"
            except Exception as exc:  # noqa: BLE001
                attempt["error"] = attempt["error"] or f"pages: {type(exc).__name__}: {exc}"[:200]
        attempt["depth"] = _depth(attempt)
        if attempt["depth"] > best["depth"]:
            best = attempt
        if attempt["depth"] == 3:
            break  # fully working — no need to try more series

    result["detail"] = best["detail"]
    result["chapters"] = best["chapters"]
    result["pages"] = best["pages"]
    result["n_chapters"] = best["n_chapters"]
    result["n_pages"] = best["n_pages"]
    result["series_sample"] = best["sample"]
    result["error"] = best["error"]
    result["ok"] = all(result[s] == "PASS" for s in STAGES)
    result["secs"] = round(time.monotonic() - t0, 1)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mature", action="store_true", help="include mature connectors")
    ap.add_argument("--only", default="", help="comma-separated source_ids to check")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=30.0, help="per-connector seconds")
    ap.add_argument("--out", default=str(REPO / "docs" / "connector_e2e_results.json"))
    args = ap.parse_args()

    descriptors = list(list_installed_connectors(include_mature=True))
    ids = [d.source_type for d in descriptors]
    if not args.mature:
        mature = {d.source_type for d in descriptors if getattr(d, "mature", False)}
        ids = [i for i in ids if i not in mature]
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        ids = [i for i in ids if i in want]
    # local_filesystem needs config; skip in the live web check
    ids = [i for i in ids if i != "local_filesystem"]

    print(f"Checking {len(ids)} connectors "
          f"(workers={args.workers}, timeout={args.timeout}s, mature={args.mature})...",
          flush=True)

    results: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(check_one, sid): sid for sid in ids}
        for fut in cf.as_completed(futs):
            sid = futs[fut]
            try:
                results.append(fut.result(timeout=args.timeout))
            except cf.TimeoutError:
                results.append({
                    "source_id": sid, "browse": "TIMEOUT", "detail": "-",
                    "chapters": "-", "pages": "-", "series_sample": "",
                    "n_series": 0, "n_chapters": 0, "n_pages": 0,
                    "error": f"timeout >{args.timeout}s", "ok": False,
                    "secs": args.timeout,
                })
            except Exception as exc:  # noqa: BLE001
                results.append({
                    "source_id": sid, "browse": "ERROR", "detail": "-",
                    "chapters": "-", "pages": "-", "series_sample": "",
                    "n_series": 0, "n_chapters": 0, "n_pages": 0,
                    "error": f"{type(exc).__name__}: {exc}"[:200], "ok": False,
                    "secs": 0.0,
                })

    results.sort(key=lambda r: (not r["ok"], r["source_id"]))
    fully_ok = [r for r in results if r["ok"]]

    def mark(v: str) -> str:
        return {"PASS": "✅", "FAIL": "❌", "TIMEOUT": "⏱", "ERROR": "💥", "-": "·"}.get(v, v)

    print()
    print(f"{'source':22} {'br':>2} {'de':>2} {'ch':>2} {'pg':>2}  {'ser/ch/pg':>12}  sample / error")
    print("-" * 100)
    for r in results:
        counts = f"{r['n_series']}/{r['n_chapters']}/{r['n_pages']}"
        tail = r["series_sample"] if r["ok"] else (r["error"] or r["series_sample"])
        print(f"{r['source_id']:22} "
              f"{mark(r['browse']):>2} {mark(r['detail']):>2} {mark(r['chapters']):>2} {mark(r['pages']):>2}  "
              f"{counts:>12}  {tail[:52]}")

    print("-" * 100)
    print(f"FULLY WORKING (browse+detail+chapters+pages): {len(fully_ok)}/{len(results)}")
    print("  " + ", ".join(r["source_id"] for r in fully_ok))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "checked": len(results),
        "fully_working": len(fully_ok),
        "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
